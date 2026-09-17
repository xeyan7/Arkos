"""Cron pre-run preflight: transient provider-resolution error classification, provider-key /
delivery-target / skills checks, and the shared-route adapter view used by satellite profiles.

Split out of ``cron.scheduler``. Import names from this module directly (``cron.scheduler`` only
imports the few it calls itself). Origin-resident helpers and sibling split modules are reached
late-bound (``_sched`` / module refs at the bottom) so monkeypatching the defining module works.
"""

from __future__ import annotations

import errno
import json
import logging
import os
from typing import Optional

logger = logging.getLogger("cron.scheduler")

BLOCKED_CONFIG_MARKER = "[blocked_config]"
BLOCKED_CONFIG_SILENT_MARKER = "[blocked_config:silent]"
DRIFT_SKIP_MARKER = "[drift_skip]"
DRIFT_SKIP_SILENT_MARKER = "[drift_skip:silent]"

_TRANSIENT_NET_EXC_NAMES = frozenset({
    "ConnectError", "ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout", "NetworkError",
    "TimeoutException", "ClientConnectorError", "ClientConnectorDNSError", "ServerTimeoutError",
    "ClientOSError"})
_DNS_FAILURE_NEEDLES = ("nodename nor servname", "name or service not known")
_TRANSIENT_OSERROR_NEEDLES = _DNS_FAILURE_NEEDLES + (
    "temporary failure in name resolution", "network is unreachable")
_TRANSIENT_HTTP_NEEDLES = _TRANSIENT_OSERROR_NEEDLES + (
    "failed to resolve", "connection refused", "timed out", "timeout")
_TRANSIENT_ERRNOS = frozenset({
    errno.ECONNREFUSED, errno.ECONNRESET, errno.EHOSTUNREACH, errno.ENETUNREACH, errno.ENETDOWN,
    errno.ETIMEDOUT, errno.EAGAIN})


def _is_transient_provider_resolve_error(exc: BaseException) -> bool:
    """True when primary provider resolution failed for a transient network reason (DNS blip,
    ConnectError...). Must be eligible for ``fallback_providers`` like AuthError, else a healthy
    fallback rung is never tried and the job dies before the first model call."""
    import socket

    eai_transient = {
        getattr(socket, n) for n in ("EAI_NONAME", "EAI_AGAIN", "EAI_FAIL", "EAI_NODATA")
        if hasattr(socket, n)
    }
    seen: set[int] = set()
    cur: Optional[BaseException] = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        module = type(cur).__module__ or ""
        msg = str(cur).lower()
        if type(cur).__name__ in _TRANSIENT_NET_EXC_NAMES:
            return True
        if any(m in module for m in ("httpx", "httpcore", "aiohttp")) and any(
            needle in msg for needle in _TRANSIENT_HTTP_NEEDLES):
            return True
        if isinstance(cur, OSError):
            if isinstance(cur, socket.gaierror):
                if cur.errno in eai_transient:
                    return True
            elif getattr(cur, "errno", None) in _TRANSIENT_ERRNOS:
                return True
            if any(needle in msg for needle in _TRANSIENT_OSERROR_NEEDLES):
                return True
        if any(needle in msg for needle in _DNS_FAILURE_NEEDLES):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def _cron_preflight_enabled(cfg: dict) -> bool:
    """Preflight is ON unless ``cron.preflight`` is literally ``false``."""
    cron_cfg = (cfg or {}).get("cron")
    return not isinstance(cron_cfg, dict) or cron_cfg.get("preflight", True) is not False


def _preflight_check_provider_key(job: dict, cfg: dict) -> Optional[str]:
    """READ-ONLY probe: would provider resolution fail for lack of a key? Mirrors run_job's
    requested-provider computation. Skipped when a fallback chain exists — auth-fallback may
    legitimately rescue a missing primary key, so blocking here would break that contract."""
    try:
        if _sched.get_fallback_chain(cfg):
            return None
    except Exception:
        return None

    _cron_cfg = cfg.get("cron") if isinstance(cfg.get("cron"), dict) else {}
    requested = (
        job.get("provider") or str((_cron_cfg or {}).get("model_provider") or "").strip() or None)
    model = job.get("model") or os.getenv("ARKOS_MODEL") or ""

    from arkos_cli.auth import AuthError
    try:
        from arkos_cli.runtime_provider import resolve_runtime_provider
        kwargs = {"requested": requested, "target_model": model}
        if job.get("base_url"):
            kwargs["explicit_base_url"] = job.get("base_url")
        resolve_runtime_provider(**kwargs)
    except AuthError as exc:
        return (
            f"provider credential missing: {exc}. "
            "Set the provider API key in .env (or `arkos setup`), or pin a "
            "working provider via `arkos cron edit "
            f"{job.get('id')} --provider <p>`."
        )
    except Exception:
        return None
    return None


def _primary_profile_routes_for_current_home() -> list:
    """Primary gateway ``profile_routes`` targeting the profile being served; ``[]`` if this IS the
    primary home. Satellite crons are ticked and delivered by the primary gateway (a satellite
    holding its own token is a ``duplicate_credential`` fatal). Reads the primary config.yaml
    directly (top-level or nested ``gateway.``) instead of ``load_gateway_config`` so no primary
    platform config leaks into this process. Shared by preflight rescue and delivery-time
    resolution so they cannot drift.

    Under ``gateway.multiplex_profiles`` a satellite profile's cron jobs are ticked by the primary gateway's
    in-process ticker and delivered through the primary gateway's live adapters — the satellite
    home never holds the platform credentials itself (giving it a token of its own is a
    ``duplicate_credential`` fatal).
    """
    try:
        from arkos_constants import get_default_arkos_root, get_arkos_home
        primary_home = get_default_arkos_root()
        current_home = _sched.Path(get_arkos_home())
        if (
            primary_home.expanduser().resolve(strict=False)
            == current_home.expanduser().resolve(strict=False)
        ):
            return []
        config_path = primary_home.expanduser() / "config.yaml"
        if not config_path.exists():
            return []

        from arkos_cli.config import read_user_config_raw
        raw = read_user_config_raw(config_path)
        routes_raw = raw.get("profile_routes")
        if routes_raw is None and isinstance(raw.get("gateway"), dict):
            routes_raw = raw["gateway"].get("profile_routes")
        if not isinstance(routes_raw, list):
            return []

        from gateway.profile_routing import parse_profile_routes
        from arkos_cli.profiles import profile_matches_home
        return [
            route for route in parse_profile_routes(routes_raw)
            if route.enabled and profile_matches_home(route.profile)
        ]
    except Exception:
        logger.debug("primary-gateway profile-route lookup unavailable", exc_info=True)
        return []


def _delivery_platform_routed_from_primary_gateway(platform_name: str) -> bool:
    """True when the primary gateway routes this platform to the profile being served.

    scheduler is currently serving (preflight rescue).
    """
    platform_key = platform_name.lower()
    return any(
        str(route.platform).lower() == platform_key
        for route in _primary_profile_routes_for_current_home()
    )


class SharedRouteAdapters:
    """Read-only adapter map for a credentialless satellite profile. ``get(platform, target)``
    resolves the PRIMARY adapter iff the inbound route matcher (``ProfileRoute.matches``) accepts
    the target; anything else (unmatched target, disabled route, other profile, or target-less
    ``get(platform)``) is a miss — fail closed, never the default bot..
    """

    def __init__(self, primary_adapters, routes) -> None:
        self._primary = dict(primary_adapters or {})
        self._routes = list(routes or [])

    def __bool__(self) -> bool:
        return bool(self._primary) and bool(self._routes)

    def get(self, platform, target=None, default=None):
        if not target:
            return default
        adapter = self._primary.get(platform)
        if adapter is None:
            return default
        platform_key = str(getattr(platform, "value", platform)).lower()
        chat_id = str(target.get("chat_id") or "") or None
        thread_id = target.get("thread_id")
        thread_id = str(thread_id) if thread_id else None
        for route in self._routes:
            if str(route.platform).lower() != platform_key:
                continue
            if not (route.chat_id or route.thread_id):
                continue
            if route.matches(str(route.platform), chat_id=chat_id, thread_id=thread_id):
                return adapter
        return default


def _preflight_check_delivery(job: dict) -> Optional[str]:
    """Check delivery targets resolve to configured platforms. ``local``/``origin``/``all`` are
    never checked (no gateway-config load). Unknown platform always blocks; known platform blocks
    only if the gateway config loads AND reports it unconnected; config load failures fail OPEN.
    ``failure_deliver`` gets the same rules — a typo'd failure platform would otherwise only
    surface when a failure occurs."""
    deliver_value = _delivery._normalize_deliver_value(job.get("deliver", "local"))
    failure_deliver_value = _delivery._normalize_deliver_value(
        _delivery._delivery_lane_value(job, for_failure=True))
    lane_values = [deliver_value]
    if failure_deliver_value != deliver_value:
        lane_values.append(failure_deliver_value)
    platform_parts: list[str] = []
    for lane_value in lane_values:
        for part in lane_value.split(","):
            part = part.strip()
            if not part or part.lower() in {"local", "origin", "all"}:
                continue
            if _delivery.parse_bot_chat_deliver_token(part) is not None:
                continue
            platform_parts.append(part.split(":", 1)[0].strip())
    if not platform_parts:
        return None

    connected: Optional[set] = None
    for platform_name in platform_parts:
        if not _delivery._is_known_delivery_platform(platform_name):
            return (
                f"delivery platform '{platform_name}' is not a known cron "
                "delivery target. Fix the job's `deliver` value or configure "
                "the platform's gateway credentials."
            )
        if connected is None:
            try:
                from gateway.config import load_gateway_config
                gateway_config = load_gateway_config()
                connected = {p.value for p in gateway_config.get_connected_platforms()}
                connected |= _delivery._relay_fronted_delivery_platforms(connected)
            except Exception:
                logger.debug(
                    "preflight: gateway config unavailable — skipping "
                    "delivery credential check", exc_info=True)
                return None
        if (
            platform_name.lower() not in connected
            and not _delivery_platform_routed_from_primary_gateway(platform_name)
        ):
            return (
                f"delivery platform '{platform_name}' has no gateway "
                "credentials configured (not connected). Configure it via "
                "`arkos setup` or change the job's `deliver` target."
            )
    return None


_SKILL_MISSING_FIELDS = (
    ("missing_required_environment_variables", "env ${}"),
    ("missing_required_commands", "command '{}'"),
    ("missing_credential_files", "credential file {}"))


def _preflight_check_skills(job: dict) -> Optional[str]:
    """Block only on an affirmative ``setup_needed`` verdict from ``skill_view``; skills that fail
    to load fall through to ``_build_job_prompt``'s skipped-skill handling (fail-open)."""
    from cron.scheduler_prompt import _job_skill_names
    skill_names = _job_skill_names(job)
    if not skill_names:
        return None
    from tools.skills_tool import skill_view
    for skill_name in skill_names:
        try:
            payload = json.loads(skill_view(skill_name))
        except Exception:
            continue
        if not isinstance(payload, dict) or not payload.get("success"):
            continue
        if payload.get("setup_needed") or payload.get("readiness_status") == "setup_needed":
            missing = [
                fmt.format(name)
                for key, fmt in _SKILL_MISSING_FIELDS
                for name in payload.get(key) or []
            ]
            detail = ", ".join(missing) or "required setup incomplete"
            return (
                f"attached skill '{skill_name}' is not ready: missing "
                f"{detail}. Provide the missing prerequisites or detach the "
                "skill from this job."
            )
    return None


def _preflight_job_config(job: dict, cfg: dict) -> Optional[str]:
    """Pre-dispatch validation: return a reason (missing key, unconfigured delivery, unready skill)
    so the caller refuses BEFORE building agent machinery or burning an LLM call. Every check fails
    open — preflight blocks only on an affirmative misconfiguration verdict.

    Same fail-before-spend spirit as the  drift guard and the fail-loud-on-hidden-tools direction in
    ; alert dedup follows the alert-once pattern from the dead-pin auto-pause.
    """
    for name, check in (
        ("provider_key", lambda: _preflight_check_provider_key(job, cfg)),
        ("skills", lambda: _preflight_check_skills(job)),
        ("delivery", lambda: _preflight_check_delivery(job))):
        try:
            reason = check()
        except Exception:
            logger.debug("preflight check %s raised — failing open", name, exc_info=True)
            continue
        if reason:
            return reason
    return None


from cron import scheduler as _sched  # noqa: E402
from cron import scheduler_delivery as _delivery  # noqa: E402
