"""Per-model stale-timeout FLOOR for known reasoning models.

Reasoning models routinely exceed the default chat-model stale detectors (stream 180s,
non-stream 90s): upstream proxies idle-kill the stream mid-think, surfacing as
``BrokenPipeError``/``RemoteProtocolError``. The stale-detector scaling applies
``max(default, floor)`` from :func:`get_reasoning_stale_timeout_floor`, so this never
overrides explicit per-model ``stale_timeout_seconds``/``request_timeout_seconds`` (that
branch never calls it), never lowers a threshold, and is ``None`` for non-allowlisted models.
"""

from __future__ import annotations

import re
from typing import Optional


_REASONING_STALE_TIMEOUT_FLOORS: dict[int, tuple[str, ...]] = {
    600: (
        "nemotron-3-ultra", "nemotron-3-super",
        "deepseek-r1", "deepseek-reasoner", "deepseek-v4-flash", "deepseek-v4-pro",
        "o1", "o1-mini", "o1-pro", "o1-preview", "o3", "o3-pro",
        "claude-fable",
    ),
    300: (
        "nemotron-3-nano", "nemotron-3.5-lightning", "qwq-32b", "o3-mini", "o4-mini",
        "grok-4-fast-reasoning", "grok-4.20-reasoning", "grok-4.5", "grok-4.6",
        "ox-alpha", "x-preview-f-free", "inkling",
    ),
    240: ("claude-opus-4", "claude-opus-5"),
    180: ("qwen3", "claude-sonnet-5", "claude-sonnet-4.5", "claude-sonnet-4.6", "grok-4-fast-non-reasoning"),
}


_SORTED_REASONING_FLOORS: list[tuple[str, float, re.Pattern[str]]] = [
    (slug, floor, re.compile(r"^" + re.escape(slug) + r"(?:$|[\-._:])"))
    for slug, floor in sorted(
        ((slug, floor) for floor, slugs in _REASONING_STALE_TIMEOUT_FLOORS.items() for slug in slugs),
        key=lambda kv: -len(kv[0]),
    )
]


def get_reasoning_stale_timeout_floor(model: object) -> Optional[float]:
    """Stale-timeout floor (seconds) for a known reasoning model, else ``None``.

    The aggregator prefix (up to the last ``/``) is stripped and the slug matched
    start-anchored with an end-or-separator right anchor, so ``qwen3-235b`` matches ``qwen3``
    but ``some-other-qwen3`` and ``llama-4-70b-o1-preview`` do not.
    """
    if not model or not isinstance(model, str):
        return None
    name = model.strip().lower().rsplit("/", 1)[-1]
    for _slug, floor, pattern in _SORTED_REASONING_FLOORS:
        if pattern.search(name):
            return float(floor)
    return None
