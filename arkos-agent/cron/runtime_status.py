"""Best-effort status of the built-in scheduler host, independent of Arkos CLI."""
from typing import Optional

def builtin_scheduler_liveness() -> Optional[bool]:
    """True for an active runtime or external scheduler; None when the host cannot be established."""
    try:
        from cron.scheduler_provider import resolve_cron_scheduler
        if resolve_cron_scheduler().name != "builtin":
            return True
        from gateway.status import is_gateway_runtime_lock_active
        return True if is_gateway_runtime_lock_active() else None
    except Exception:
        return None
