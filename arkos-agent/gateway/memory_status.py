"""Memory status rollup for ``/api/status``.

Read side for signals the gateway already persists: the 30s ``state/gateway.heartbeat``
(RSS + MemAvailable/MemTotal + swap) and the lifecycle sentinel's ``suspected_oom``
flag — two small file reads, no IPC.  ``/api/status`` is unauthenticated, so only
coarse numbers (MB), enums and booleans.  A missing/corrupt file degrades to
``pressure="unknown"`` rather than raising into the status endpoint.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_CRITICAL_AVAILABLE_KIB = 64 * 1024
_CRITICAL_AVAILABLE_FRACTION = 0.05
_ELEVATED_AVAILABLE_KIB = 128 * 1024
_ELEVATED_AVAILABLE_FRACTION = 0.15
_PRESSURE_TIERS = (
    ("critical", _CRITICAL_AVAILABLE_KIB, _CRITICAL_AVAILABLE_FRACTION),
    ("elevated", _ELEVATED_AVAILABLE_KIB, _ELEVATED_AVAILABLE_FRACTION),
)

_HEARTBEAT_FRESH_TTL_S = 150.0


def _nonneg_int(value: Any) -> Optional[int]:
    """Return *value* if it is a non-negative int (bools rejected), else None."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _mb(kib: Any) -> Optional[int]:
    return None if _nonneg_int(kib) is None else kib // 1024


def _parse_iso(value: Any) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) and value else None
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed is not None and parsed.tzinfo is None else parsed


def classify_pressure(available_kib: Any, total_kib: Any) -> str:
    """``ok``/``elevated``/``critical`` from MemAvailable/MemTotal; ``unknown`` when the
    sample is missing/malformed — "could not read it" must never read as "fine"."""
    available, total = _nonneg_int(available_kib), _nonneg_int(total_kib)
    if available is None:
        return "unknown"
    fraction = available / total if total else None
    for level, kib_floor, frac_floor in _PRESSURE_TIERS:
        if available < kib_floor or (fraction is not None and fraction < frac_floor):
            return level
    return "ok"


def _read_state_files(home: Optional[Path]) -> tuple:
    """``(heartbeat, sentinel)`` dicts, each ``None`` when unreadable."""
    try:
        from gateway.lifecycle_ledger import _read_json, get_lifecycle_sentinel_path
        from gateway.shutdown_watchdog import get_loop_heartbeat_path

        return _read_json(get_loop_heartbeat_path(home)), _read_json(get_lifecycle_sentinel_path(home))
    except Exception:
        return None, None


def collect_memory_status(
    home: Optional[Path] = None,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """``memory`` block for ``/api/status``; ``home`` scopes to a profile (``None`` =
    active), ``now`` is injectable.  Never raises — a down gateway or corrupt files
    yield ``pressure="unknown"`` plus whatever fields could be recovered."""
    moment = now or datetime.now(timezone.utc)
    status: Dict[str, Any] = {
        "pressure": "unknown", "gateway_rss_mb": None, "system_total_mb": None, "system_available_mb": None,
        "swap_used_mb": None, "sampled_at": None, "last_boot_unclean": False, "last_boot_suspected_oom": False,
        "boot_id": None,
    }

    heartbeat, sentinel = _read_state_files(home)
    if heartbeat:
        sampled_at, mem = _parse_iso(heartbeat.get("updated_at")), heartbeat.get("mem")
        if isinstance(mem, dict):
            for dst, src in (("gateway_rss_mb", "rss_kib"), ("system_total_mb", "mem_total_kib"),
                             ("system_available_mb", "mem_available_kib"), ("swap_used_mb", "swap_used_kib")):
                status[dst] = _mb(mem.get(src))
            if sampled_at is not None:
                status["sampled_at"] = sampled_at.isoformat()
                if 0 <= (moment - sampled_at).total_seconds() <= _HEARTBEAT_FRESH_TTL_S:
                    status["pressure"] = classify_pressure(mem.get("mem_available_kib"), mem.get("mem_total_kib"))

    if sentinel:
        status["last_boot_unclean"] = bool(sentinel.get("prior_unclean_exit"))
        status["last_boot_suspected_oom"] = bool(sentinel.get("prior_suspected_oom"))
        started_at = sentinel.get("started_at")
        status["boot_id"] = started_at if isinstance(started_at, str) and started_at else None

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
