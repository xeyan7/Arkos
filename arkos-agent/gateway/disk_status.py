"""Disk-usage rollup for ``/api/status``.

Companion to :mod:`gateway.memory_status`: a hosted agent can fill its data
volume (SQLite writes failing, config saves lost) while its dashboard looks
healthy.  Sampled live via one ``statvfs`` call, so there is no ``sampled_at``.
``/api/status`` is unauthenticated: only coarse numbers (MB, one-decimal
percent) and an enum.  Best-effort: an unreadable filesystem degrades to
``pressure="unknown"`` rather than raising into the status endpoint.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from gateway.memory_status import _nonneg_int

_PRESSURE_TIERS = (
    ("critical", 256, 95.0, 1024),
    ("elevated", 512, 85.0, 4096),
)
_BYTES_PER_MB = 1024 * 1024


def classify_disk_pressure(free_mb: Any, total_mb: Any) -> str:
    """``ok``/``elevated``/``critical`` from free/total MB; ``unknown`` when the sample
    is missing/malformed — "could not read it" must never read as "fine"."""
    free, total = _nonneg_int(free_mb), _nonneg_int(total_mb)
    if free is None or not total:
        return "unknown"
    used_percent = (1 - free / total) * 100.0
    for level, free_floor, percent_floor, headroom in _PRESSURE_TIERS:
        if free < free_floor or (used_percent >= percent_floor and free < headroom):
            return level
    return "ok"


def collect_disk_status(home: Optional[Path] = None) -> Dict[str, Any]:
    """``disk`` block for ``/api/status`` (same ``home`` contract as ``memory``).
    Never raises — an unreadable/unmounted filesystem yields ``pressure="unknown"``."""
    status: Dict[str, Any] = {"pressure": "unknown", "total_mb": None, "free_mb": None, "used_percent": None}
    try:
        if home is None:
            from arkos_constants import get_arkos_home

            home = get_arkos_home()
        usage = shutil.disk_usage(home)
    except Exception:
        return status
    if usage.total <= 0:
        return status
    total_mb, free_mb = usage.total // _BYTES_PER_MB, usage.free // _BYTES_PER_MB
    status.update(total_mb=total_mb, free_mb=free_mb, used_percent=round((usage.used / usage.total) * 100, 1),
                  pressure=classify_disk_pressure(free_mb, total_mb))
    return status


import logging  # noqa: F401,E402


_PLUGIN_COMPAT_LAZY = {
    'logger': ('gateway.run', 'logger'),
}


def __getattr__(name):
    target = _PLUGIN_COMPAT_LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    from arkos_cli.plugin_compat import warn_once
    warn_once(__name__, name, *target)
    return getattr(importlib.import_module(target[0]), target[1])
