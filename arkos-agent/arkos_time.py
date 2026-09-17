"""Timezone-aware clock for Arkos.

``now()`` returns a tz-aware datetime in the user's configured IANA timezone. Resolution order:
``ARKOS_TIMEZONE`` env var, then ``timezone`` in ``~/.arkos/config.yaml``, else server-local
time. Invalid timezone values log a warning and fall back — never crash.
"""

import logging
import os
import threading
from datetime import datetime
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from arkos_constants import get_config_path

logger = logging.getLogger(__name__)

_cache_lock = threading.Lock()
_tz_cache: Dict[Tuple[str, str], Tuple[str, Optional[ZoneInfo]]] = {}


def _timezone_cache_identity() -> Tuple[str, str]:
    tz_env = os.getenv("ARKOS_TIMEZONE", "").strip()
    return ("environment", tz_env) if tz_env else ("config", str(get_config_path()))


def _resolve_timezone_name() -> str:
    """Read the configured IANA timezone string (or ``""``). Does file I/O — callers cache."""
    tz_env = os.getenv("ARKOS_TIMEZONE", "").strip()
    if tz_env:
        return tz_env
    try:
        try:
            from arkos_cli.config import read_raw_config
            cfg = read_raw_config() or {}
        except Exception:
            import yaml
            config_path = get_config_path()
            cfg = (yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}) if config_path.exists() else {}
        if cfg:
            try:
                from arkos_cli import managed_scope
                cfg = managed_scope.apply_managed_overlay(cfg)
            except Exception:
                pass
            tz_cfg = cfg.get("timezone", "")
            if isinstance(tz_cfg, str) and tz_cfg.strip():
                return tz_cfg.strip()
    except Exception:
        pass
    return ""


def get_timezone() -> Optional[ZoneInfo]:
    """Return the active profile's configured ZoneInfo, or None (server-local)."""
    cache_identity = _timezone_cache_identity()
    with _cache_lock:
        entry = _tz_cache.get(cache_identity)
        if entry is not None:
            return entry[1]
    name = _resolve_timezone_name()
    tz = None
    if name:
        try:
            tz = ZoneInfo(name)
        except Exception as exc:
            logger.warning("Invalid timezone '%s': %s. Falling back to server local time.", name, exc)
    with _cache_lock:
        return _tz_cache.setdefault(cache_identity, (name, tz))[1]


def reset_cache() -> None:
    """Clear the cached timezone so the next call re-resolves it (after config/env changes)."""
    with _cache_lock:
        _tz_cache.clear()


def now() -> datetime:
    """Current time as a tz-aware datetime: configured zone, else server-local."""
    tz = get_timezone()
    return datetime.now(tz) if tz is not None else datetime.now().astimezone()
