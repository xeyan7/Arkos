"""Wake-word hotword engines (openWakeWord / sherpa-onnx KWS / Porcupine).

All three run fully on-device. Config, platform probes and sensitivity accessors
live in :mod:`tools.wake_word`; engines read them lazily through that module (import cycle).
"""

from __future__ import annotations

import logging
import os
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("tools.wake_word")


def _ww():
    from tools import wake_word
    return wake_word


def _ensure_dep(feature: str) -> None:
    from tools import lazy_deps
    lazy_deps.ensure(feature, prompt=False)


class _Engine:
    """Minimal hotword-engine contract: feed int16 frames, get a bool. Subclasses set ``feature``
    (lazy_deps name, ensured before ``_build``) and their own ``cfg`` sub-section ``section``."""

    feature: str = ""
    section: str = ""
    frame_length: int = 1280

    last_match: Optional[tuple[str, str]] = None

    def __init__(self, cfg: Dict[str, Any]):
        _ensure_dep(self.feature)
        self._build(cfg, _sub(cfg, self.section), _ww())

    def _build(self, cfg: Dict[str, Any], sub: Dict[str, Any], ww) -> None:
        raise NotImplementedError

    def process(self, frame) -> bool:
        raise NotImplementedError

    def reset(self) -> None:
        """Clear any internal audio/feature buffer (called on every (re)start)."""

    def close(self) -> None:
        """Release engine resources (called once on stop)."""


def _looks_like_path(value: str) -> bool:
    return os.sep in value or value.endswith((".onnx", ".tflite", ".ppn")) or os.path.exists(value)


def _sub(cfg: Dict[str, Any], key: str) -> Dict[str, Any]:
    sub = cfg.get(key)
    return sub if isinstance(sub, dict) else {}


class _OpenWakeWordEngine(_Engine):
    """openWakeWord — free, local ONNX/tflite hotword detection. Scores one ~80 ms frame at a time;
    ``sensitivity`` IS the raw 0..1 threshold (higher = stricter). A real utterance holds the score
    high across frames while a stray phoneme spikes one, so ``confirmation_frames`` hits are required."""

    feature, section = "wake.openwakeword", "openwakeword"
    frame_length = 1280

    def _build(self, cfg, sub, ww) -> None:
        import openwakeword
        from openwakeword.model import Model
        model_ref = str(sub.get("model") or ww._BUNDLED_MODEL_NAME).strip()
        framework = self._usable_framework(ww.resolve_inference_framework(cfg))
        self._threshold = ww._sensitivity(cfg)
        self._confirm_needed = ww._confirmation_frames(cfg)
        self._confirm_streak = 0
        if model_ref.lower() in ww._BUNDLED_MODEL_ALIASES:
            model_ref = ww._bundled_wakeword_path(framework)
        try:
            openwakeword.utils.download_models([model_ref])
        except Exception as e:  # pragma: no cover - network/path dependent
            logger.debug("openwakeword model download skipped: %s", e)
        self._model = Model(wakeword_models=[model_ref], inference_framework=framework)
        self._labels = list(self._model.models.keys())

    @staticmethod
    def _usable_framework(framework: str) -> str:
        """Refuse openWakeWord's silent tflite→onnx downgrade: without a tflite runtime it falls back
        to onnx, which on macOS ARM64 never fires (armed but deaf). Install + bridge the runtime first
        (gate lives here because dep specs can't carry PEP 508 markers); on that Mac raise instead."""
        ww = _ww()
        if framework != "tflite" or ww.ensure_tflite_runtime():
            return framework
        try:
            _ensure_dep("wake.openwakeword.tflite")
        except Exception as e:
            logger.debug("wake word: tflite runtime install failed: %s", e)
        if ww.ensure_tflite_runtime():
            return framework
        if ww._is_macos_arm64():
            raise RuntimeError("The wake word needs the tflite backend on this Mac, but its "
                               "runtime is missing. Install it with: pip install ai-edge-litert")
        logger.warning("wake word: no tflite runtime available — falling back to onnx")
        return "onnx"

    def process(self, frame) -> bool:
        hit = any(score >= self._threshold for score in self._model.predict(frame).values())
        self._confirm_streak = self._confirm_streak + 1 if hit else 0
        if self._confirm_streak < self._confirm_needed:
            return False
        self._confirm_streak = 0
        return True

    def reset(self) -> None:
        self._confirm_streak = 0
        with suppress(Exception):
            self._model.reset()

    def close(self) -> None:
        self.reset()


_SHERPA_KWS_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/"
    "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2"
)
_SHERPA_KWS_MODEL_DIR = "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"


def _sherpa_model_root() -> Path:
    from arkos_constants import get_arkos_home
    return get_arkos_home() / "cache" / "wakewords"


def _ensure_sherpa_model(root: Optional[Path] = None) -> Path:
    """Download + unpack the sherpa KWS model once; return its directory."""
    root = root or _sherpa_model_root()
    target = root / _SHERPA_KWS_MODEL_DIR
    if (target / "tokens.txt").exists():
        return target
    import tarfile
    import urllib.request
    root.mkdir(parents=True, exist_ok=True)
    archive = root / f"{_SHERPA_KWS_MODEL_DIR}.tar.bz2"
    logger.info("wake word: downloading sherpa KWS model (one-time, ~13 MB)")
    urllib.request.urlretrieve(_SHERPA_KWS_MODEL_URL, archive)  # noqa: S310
    with tarfile.open(archive, "r:bz2") as tf:
        tf.extractall(root, filter="data")
    archive.unlink(missing_ok=True)
    if not (target / "tokens.txt").exists():
        raise RuntimeError(f"sherpa KWS model unpack failed: {target}")
    return target


class _SherpaKwsEngine(_Engine):
    """sherpa-onnx open-vocabulary keyword spotting — any typed phrase, zero training. ``wake_word.phrase``
    is BPE-tokenized at runtime against the model's vocabulary: DETECTION config, not a cosmetic label."""

    feature, section = "wake.sherpa", "sherpa"
    frame_length = 1280

    def _build(self, cfg, sub, ww) -> None:
        import sherpa_onnx
        import tempfile
        from sherpa_onnx import text2token
        model_dir = str(sub.get("model_dir") or "").strip()
        d = Path(model_dir) if model_dir else _ensure_sherpa_model()
        if not (d / "tokens.txt").exists():
            raise RuntimeError(f"sherpa KWS model not found at {d}")

        phrase = str(ww._get(cfg, "phrase") or "hey arkos").strip()
        phrase_map: Dict[str, str] = {phrase: ww._active_profile_name()}
        if bool(cfg.get("profile_routing", True)):
            for prof, p in ww.enrolled_profile_phrases().items():
                phrase_map.setdefault(p.strip(), prof)
        phrases = list(phrase_map)
        tokens = text2token([p.upper() for p in phrases], tokens=str(d / "tokens.txt"), tokens_type="bpe",
                            bpe_model=str(d / "bpe.model"))
        self._display_to_profile: Dict[str, str] = {}
        kw = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", prefix="arkos-kws-", delete=False,
                                         encoding="utf-8")
        for p, toks in zip(phrases, tokens):
            display = p.upper().replace(" ", "_")
            self._display_to_profile[display] = phrase_map[p]
            kw.write(" ".join(toks) + f" @{display}\n")
        kw.close()
        self._keywords_file = kw.name

        threshold = 0.05 + 0.4 * ww._sensitivity(cfg)

        def _model_file(part: str) -> str:
            hits = sorted(d.glob(f"{part}-*[!8].onnx"))
            if not hits:
                raise RuntimeError(f"sherpa KWS model file missing: {d}/{part}-*[!8].onnx")
            return str(hits[0])

        self._spotter = sherpa_onnx.KeywordSpotter(
            tokens=str(d / "tokens.txt"), encoder=_model_file("encoder"), decoder=_model_file("decoder"),
            joiner=_model_file("joiner"), keywords_file=self._keywords_file, keywords_threshold=threshold,
            num_threads=1,
        )
        self._stream = self._spotter.create_stream()

    def process(self, frame) -> bool:
        import numpy as np
        self._stream.accept_waveform(_ww().SAMPLE_RATE, np.asarray(frame, dtype=np.float32) / 32768.0)
        fired = False
        while self._spotter.is_ready(self._stream):
            self._spotter.decode_stream(self._stream)
            result = self._spotter.get_result(self._stream)
            if result:
                fired, display = True, str(result)
                self.last_match = (display.replace("_", " ").lower(),
                                   self._display_to_profile.get(display, ""))
                self._spotter.reset_stream(self._stream)
        return fired

    def reset(self) -> None:
        with suppress(Exception):
            self._stream = self._spotter.create_stream()

    def close(self) -> None:
        with suppress(OSError):
            os.unlink(self._keywords_file)


class _PorcupineEngine(_Engine):
    """Picovoice Porcupine — premium, on-device, needs an access key."""

    feature, section = "wake.porcupine", "porcupine"

    def _build(self, cfg, sub, ww) -> None:
        import pvporcupine
        access_key = (os.getenv("PORCUPINE_ACCESS_KEY") or "").strip()
        if not access_key:
            raise RuntimeError("Porcupine wake word requires PORCUPINE_ACCESS_KEY "
                               "(get a free key at https://console.picovoice.ai).")
        keyword = str(sub.get("keyword") or "jarvis").strip()
        kwargs: Dict[str, Any] = {"access_key": access_key, "sensitivities": [1.0 - ww._sensitivity(cfg)]}
        kwargs["keyword_paths" if _looks_like_path(keyword) else "keywords"] = [keyword]
        self._porcupine = pvporcupine.create(**kwargs)
        self.frame_length = self._porcupine.frame_length

    def process(self, frame) -> bool:
        return self._porcupine.process(frame) >= 0

    def close(self) -> None:
        with suppress(Exception):
            self._porcupine.delete()
