"""Canonical reasoning-effort vocabulary and wire clamping.

Arkos' internal effort ladder (``VALID_REASONING_EFFORTS`` plus ``none``) is wider than any
single provider wire accepts; hand-rolled per-transport maps leaked new levels (``ultra``) to
wires that 400 and inverted the ladder (unknown → weak default). Single source of truth:
:data:`EFFORT_LADDER` (low→high), :func:`clamp_effort` (verbatim if supported, else the
nearest WEAKER level; only when nothing weaker exists the weakest supported), and named
wire-vocabulary constants so call sites declare data. Rules: wire shape stays local, only the
vocabulary math lives here; unset stays unset (never invent an effort); when a provider
rejects a level fix its declared set, never a predicate.
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

_KIMI_K3_SLUG_RE = re.compile(r"(?:^|[^a-z0-9])k3(?:[^a-z0-9]|$)")

EFFORT_LADDER: tuple[str, ...] = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")

OPENAI_COMPAT_WIRE_EFFORTS: tuple[str, ...] = ("none", "minimal", "low", "medium", "high", "xhigh", "max")

CODEX_GPT56_EFFORTS: tuple[str, ...] = ("none", "low", "medium", "high", "xhigh", "max")
CODEX_LEGACY_EFFORTS: tuple[str, ...] = ("none", "low", "medium", "high", "xhigh")
CODEX_ASTRA_EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")
ASTRA_MODEL_IDS: frozenset[str] = frozenset({"gpt-6-astra", "gpt-6-astra-900k"})

XAI_GROK46_EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh")
XAI_LEGACY_EFFORTS: tuple[str, ...] = ("low", "medium", "high")

ACTUAL_RELAY_EFFORTS: tuple[str, ...] = ("none", "low", "medium", "high", "max")

KIMI_K3_EFFORTS: tuple[str, ...] = ("low", "high", "max")
KIMI_K2_EFFORTS: tuple[str, ...] = ("low", "medium", "high")
KIMI_K3_OVERRIDES: dict[str, str] = {"medium": "high", "xhigh": "max"}

OX_ALPHA_EFFORTS: tuple[str, ...] = ("low", "high", "max")
OX_ALPHA_OVERRIDES: dict[str, str] = {"xhigh": "max"}

TOKENHUB_EFFORTS: tuple[str, ...] = ("low", "medium", "high")
NEBIUS_EFFORTS: tuple[str, ...] = ("low", "medium", "high")
SOLAR_EFFORTS: tuple[str, ...] = ("low", "medium", "high")

GLM52_EFFORTS: tuple[str, ...] = ("high", "max")
GLM52_OVERRIDES: dict[str, str] = {"xhigh": "max"}
GLM53_EFFORTS: tuple[str, ...] = ("low", "medium", "high", "max")
GLM53_OVERRIDES: dict[str, str] = {"xhigh": "max"}

DEEPSEEK_V4_EFFORTS: tuple[str, ...] = ("low", "medium", "high", "max")
DEEPSEEK_V4_OVERRIDES: dict[str, str] = {"xhigh": "max"}

OLLAMA_CLOUD_EFFORTS: tuple[str, ...] = ("none", "low", "medium", "high", "max")
OLLAMA_CLOUD_OVERRIDES: dict[str, str] = {"xhigh": "max"}

META_AI_EFFORTS: tuple[str, ...] = ("minimal", "low", "medium", "high", "xhigh")


def is_astra_model(model: Optional[str]) -> bool:
    """``gpt-6-astra`` or its Arkos-side ``-900k`` picker alias, with or without a ``vendor/`` prefix.
    The single home for the slug set: picker gating, effort vocabulary and the request sanitizer all
    key off it, so a new Astra alias is one edit."""
    return (model or "").strip().lower().rsplit("/", 1)[-1] in ASTRA_MODEL_IDS


def codex_supported_efforts(model: Optional[str]) -> tuple[str, ...]:
    """Supported effort set for an OpenAI/Codex Responses model."""
    if is_astra_model(model):
        return CODEX_ASTRA_EFFORTS
    return CODEX_GPT56_EFFORTS if "gpt-5.6" in (model or "").lower() else CODEX_LEGACY_EFFORTS


def kimi_supported_efforts(model: Optional[str]) -> tuple[str, ...]:
    """Supported effort set for a Moonshot/Kimi slug (bare ``k3``, ``k3-256k``, ``kimi-k3*`` → K3).

    K3 is served as the bare slug ``k3``, plan variants like ``k3-256k``, and the ``kimi-k3*`` aliases; its
    documented set is low/high/max. Everything earlier speaks low/medium/high. Boundary-matched so K2-era
    names (``kimi-k2.6``) never match.
    """
    m = (model or "").strip().lower().split("/")[-1]
    return KIMI_K3_EFFORTS if _KIMI_K3_SLUG_RE.search(m) else KIMI_K2_EFFORTS


def clamp_effort(
    effort: Optional[str], supported: Optional[Sequence[str]], overrides: Optional[dict[str, str]] = None,
) -> Optional[str]:
    """Clamp a requested reasoning effort onto a wire's supported levels.

    ``overrides`` (a declared vendor mapping, e.g. Kimi K3 ``medium → high``) is consulted
    first. Otherwise the request passes through unchanged when it is supported, when the
    supported set is unknown/empty, or when it isn't a recognized ladder level (custom
    providers may use bespoke names). Else the **nearest weaker** supported level is returned
    so a clamp never escalates cost; when nothing weaker exists, the weakest supported level
    (the provider's floor is the closest honest match). Monotonic: a stronger request never
    resolves weaker than a weaker request would.
    """
    requested = str(effort or "").strip().lower()
    if not requested or not supported:
        return effort
    supported_norm = [lvl for lvl in (str(s).strip().lower() for s in supported) if lvl in EFFORT_LADDER]
    if not supported_norm or requested in supported_norm:
        return effort
    if overrides and overrides.get(requested) in supported_norm:
        return overrides[requested]
    if requested not in EFFORT_LADDER:
        return effort
    candidates = [level for level in supported_norm if level != "none"]
    if not candidates:
        return effort
    requested_idx = EFFORT_LADDER.index(requested)
    below = [level for level in candidates if EFFORT_LADDER.index(level) < requested_idx]
    return max(below, key=EFFORT_LADDER.index) if below else min(candidates, key=EFFORT_LADDER.index)


def requested_effort(reasoning_config: Optional[dict]) -> Optional[str]:
    """The user's explicit effort, or None (absent/malformed config, no effort, or reasoning
    disabled) — callers then omit the wire field."""
    if not isinstance(reasoning_config, dict) or reasoning_config.get("enabled") is False:
        return None
    return str(reasoning_config.get("effort") or "").strip().lower() or None



CODEX_RESPONSES_EFFORTS: tuple[str, ...] = CODEX_GPT56_EFFORTS
