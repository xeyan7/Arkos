"""Offline dependency readiness and recovery metadata for engine tools."""

from __future__ import annotations


import logging


import shutil


import sys


from pathlib import Path


from tools.cua_install import (
    _cua_driver_install_ready, _pip_install, _post_setup_no_window_flags, _run_text, install_cua_driver,
)


PROJECT_ROOT = Path(__file__).parent.parent.resolve()


_KITTENTTS_WHEEL_URL = "https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl"


def _pip_hook(module, label, installing, args, manual, on_install=(), always=()) -> dict:
    return {"module": module, "label": label, "installing": installing, "args": args, "manual": manual,
            "on_install": on_install, "always": always}


_PIP_POST_SETUP_HOOKS: dict = {
    "faster_whisper": _pip_hook(
        "faster_whisper", "faster-whisper", "Installing faster-whisper (model ~150MB downloads on first use)...",
        ["-U", "faster-whisper", "--quiet"], "uv pip install -U faster-whisper",
        on_install=("Model sizes: tiny, base (default), small, medium, large-v3",
                    "Change via stt.local.model in ~/.arkos/config.yaml")),
    "kittentts": _pip_hook(
        "kittentts", "kittentts", "Installing kittentts (~25-80MB model, CPU-only)...",
        ["-U", _KITTENTTS_WHEEL_URL, "soundfile", "--quiet"], f"uv pip install -U '{_KITTENTTS_WHEEL_URL}' soundfile",
        on_install=("Voices: Jasper, Bella, Luna, Bruno, Rosie, Hugo, Kiki, Leo",
                    "Models: KittenML/kitten-tts-nano-0.8-int8 (25MB), micro (41MB), mini (80MB)")),
    "piper": _pip_hook(
        "piper", "piper-tts", "Installing piper-tts (~14MB wheel, voices downloaded on first use)...",
        ["-U", "piper-tts", "--quiet"], "uv pip install -U piper-tts",
        always=("Default voice: en_US-lessac-medium (downloaded on first TTS call)",
                "Full voice list: https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md",
                "Switch voices by setting tts.piper.voice in ~/.arkos/config.yaml")),
    "ddgs": _pip_hook(
        "ddgs", "ddgs", "Installing ddgs (DuckDuckGo search package)...", ["-U", "ddgs", "--quiet"],
        "uv pip install -U ddgs",
        always=("No API key required. DuckDuckGo enforces server-side rate limits.",
                "Pair with an extract provider if you also need web_extract."))}


_POST_SETUP_INSTALLED: dict = {"cua_driver": lambda: _cua_driver_install_ready()}


def _post_setup_already_installed(post_setup_key: str) -> bool:
    """Return True when the post_setup install side-effect is satisfied (or no check is registered)."""
    predicate = _POST_SETUP_INSTALLED.get(post_setup_key)
    try:
        return predicate is None or bool(predicate())
    except Exception:
        return True


def _module_installed(module_name: str) -> bool:
    """Cheap importable-without-importing check (no heavy side effects)."""
    import importlib.util
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


_RESTORABLE_PYTHON_TOOL_DEPENDENCIES: dict[str, tuple[str, tuple[str, ...]]] = {
    **{key: (spec["module"], tuple(a for a in spec["args"] if a != "--quiet"))
       for key, spec in _PIP_POST_SETUP_HOOKS.items()},
    "langfuse": ("langfuse", ("langfuse",))}


def active_restorable_python_tool_dependencies() -> list[str]:
    """Return ``arkos tools`` Python dependencies present in this runtime."""
    return [
        name for name, (module_name, _install_args) in _RESTORABLE_PYTHON_TOOL_DEPENDENCIES.items()
        if _module_installed(module_name)]


def restorable_python_tool_dependency(name: str) -> tuple[str, tuple[str, ...]] | None:
    """Return the import probe and pip arguments for an allowlisted tool."""
    return _RESTORABLE_PYTHON_TOOL_DEPENDENCIES.get(name)


def _agent_browser_installed() -> bool:
    """Whether the local browser CLI is installed."""
    if (bt := sys.modules.get("tools.browser_tool")) is not None:
        bt._cached_chromium_installed = None
    return shutil.which("agent-browser") is not None


def _camofox_installed() -> bool:
    """True when the Camofox npm package ``_run_post_setup("camofox")`` installs is in node_modules."""
    return (PROJECT_ROOT / "node_modules" / "@askjo" / "camofox-browser").exists()


def _lightpanda_installed() -> bool:
    """True when a lightpanda binary is on PATH or in a known install dir."""
    try:
        from tools.browser_lightpanda import find_lightpanda_binary
        return find_lightpanda_binary() is not None
    except Exception:
        return False


def _cloud_agent_browser_installed() -> bool:
    return shutil.which("agent-browser") is not None


_POST_SETUP_READY: dict = {
    **{key: (lambda m=module: _module_installed(m)) for key, (module, _args) in _RESTORABLE_PYTHON_TOOL_DEPENDENCIES.items()},
    "agent_browser": lambda: _agent_browser_installed(),
    "browserbase": lambda: _cloud_agent_browser_installed(),
    "camofox": lambda: _camofox_installed(),
    "lightpanda": lambda: _lightpanda_installed(),
    "cua_driver": lambda: _cua_driver_install_ready()}

logger = logging.getLogger(__name__)
