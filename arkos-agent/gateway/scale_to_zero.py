"""Scale-to-zero idle detection + dormant-quiesce for the gateway.

Owns the *decision* to go idle, drives the relay transport's ``go_dormant()``, then SUSPENDS the
machine via the local Fly Machines API socket; wake stays platform-side (autostart on wakeUrl).
Self-suspend because Fly Proxy only sees INBOUND proxied connections: it would suspend mid-turn or
before ``go_dormant()`` flipped the relay destination (buffered-event black hole). Enable is gated
SOLELY by the Portal "Labs" toggle env stamp (not config); the idle timeout IS config.yaml. Quiesce
uses ``go_dormant()`` (never disconnect/drain); ``mark_resume_pending`` is NOT called: suspend
preserves RAM."""

from __future__ import annotations

import json
import logging
import os
import socket
import time
import urllib.parse
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

SCALE_TO_ZERO_ENV = "ARKOS_SCALE_TO_ZERO"
FLY_APP_NAME_ENV = "FLY_APP_NAME"
FLY_MACHINE_ID_ENV = "FLY_MACHINE_ID"
FLY_API_SOCKET = "/.fly/api"

SLEEP_URL_ENV = "GATEWAY_RELAY_SLEEP_URL"

_malformed_sleep_url_logged = False

DEFAULT_IDLE_TIMEOUT_MINUTES = 2
_TRUTHY = {"1", "true", "yes", "on"}
DASHBOARD_CLIENT_HEARTBEAT_REL = os.path.join("state", "dashboard_clients.heartbeat")


def _env_str(env: Optional[dict], key: str) -> str:
    return str((os.environ if env is None else env).get(key, "")).strip()


def scale_to_zero_enabled(environ: Optional[dict] = None) -> bool:
    """Whether the Labs toggle stamp is set. Absent/blank/falsey -> disabled."""
    return _env_str(environ, SCALE_TO_ZERO_ENV).lower() in _TRUTHY


def parse_idle_timeout_seconds(cfg_value: Any,
                               default_minutes: int = DEFAULT_IDLE_TIMEOUT_MINUTES) -> float:
    """Coerce ``scale_to_zero.idle_timeout_minutes`` to seconds. Non-numeric / non-positive
    degrades to the default (never <= 0: instant dormancy)."""
    try:
        minutes = float(cfg_value)
    except (TypeError, ValueError):
        minutes = 0.0
    return (float(default_minutes) if minutes <= 0 else minutes) * 60.0


def messaging_is_relay_only_or_absent(platforms: Iterable[Any]) -> bool:
    """True iff the only connected platform is RELAY, or there is none. A directly-connected
    platform holds a live socket and cannot scale to zero. Compared by ``.value``/name so this
    module stays enum-import-free."""
    names = {str(getattr(p, "value", p)).strip().lower() for p in platforms}
    names.discard("relay")
    return not names


def should_arm(*, enabled: bool, relay_only_or_absent: bool, wake_url: Optional[str]) -> bool:
    """Arm only if ALL hold: flag on, relay-only/absent messaging, wakeUrl registered
    (a suspended instance with no wake target is a black hole). Otherwise the watcher
    never starts, so a non-opted instance behaves exactly as before."""
    return bool(enabled) and bool(relay_only_or_absent) and bool(wake_url)


def is_idle(*, active_work_count: int, seconds_since_last_inbound: float,
            idle_timeout_seconds: float, has_live_background_work: bool) -> bool:
    """Pure idle predicate: no active work, no inbound within the window, no live background work.
    ``active_work_count`` is the BROAD aggregate (agent turns + cron + API runs) — passing only
    ``len(_running_agents)`` reopens the mid-cron-job suspend hole. Callers that cannot read a
    work source must fail AWAKE (pass a positive sentinel), never fail to 0."""
    return (active_work_count <= 0 and not has_live_background_work
            and seconds_since_last_inbound >= idle_timeout_seconds)


def dashboard_client_heartbeat_path(arkos_home: Optional[os.PathLike | str] = None):
    """Path of the dashboard-client liveness marker under ARKOS_HOME."""
    if arkos_home is None:
        from arkos_constants import get_arkos_home
        arkos_home = get_arkos_home()
    return Path(arkos_home) / DASHBOARD_CLIENT_HEARTBEAT_REL


def touch_dashboard_client_heartbeat(path: Optional[os.PathLike | str] = None) -> bool:
    """Mark "a dashboard client is attached right now". Best-effort, never raises."""
    try:
        p = dashboard_client_heartbeat_path() if path is None else path
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "a", encoding="utf-8").close()
        os.utime(p, None)
        return True
    except Exception:  # noqa: BLE001 - liveness garnish must never break the WS
        logger.debug("scale-to-zero: dashboard heartbeat touch failed", exc_info=True)
        return False


def dashboard_client_last_seen(path: Optional[os.PathLike | str] = None, *,
                               now: Optional[float] = None) -> Optional[float]:
    """Epoch seconds a dashboard client last sent a WS frame, or None if never. Missing marker ->
    None (steady state when nobody has the dashboard open — NOT fail-awake, or no instance would
    ever sleep). Unreadable marker -> ``now`` (fail-awake, as in ``is_idle``). Clamped to now: an
    NTP step-back can leave the mtime in the future."""
    current = time.time() if now is None else now
    p = dashboard_client_heartbeat_path() if path is None else path
    try:
        return min(os.stat(p).st_mtime, current)
    except FileNotFoundError:
        return None
    except OSError:
        return current


def self_suspend_available(environ: Optional[dict] = None) -> bool:
    """True iff Fly machine identity is present AND the local Machines API socket exists.
    Off-Fly this is False; see ``suspend_available`` for whether some OTHER lever exists
    before concluding the watcher must abstain."""
    return bool(_env_str(environ, FLY_APP_NAME_ENV) and _env_str(environ, FLY_MACHINE_ID_ENV)
                and os.path.exists(FLY_API_SOCKET))


def brokered_sleep_url(environ: Optional[dict] = None) -> Optional[str]:
    """The Portal sleep endpoint to POST, or None when this backend has no broker.

    Validated here rather than at POST time: a malformed value would otherwise let
    the watcher mark draining, hold the re-dial and flip the connector before
    urllib rejected it, quiescing for a suspend that could never happen.
    """
    env = environ if environ is not None else os.environ
    url = str(env.get(SLEEP_URL_ENV, "")).strip()
    if not url:
        return None
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        global _malformed_sleep_url_logged
        if not _malformed_sleep_url_logged:
            _malformed_sleep_url_logged = True
            logger.warning(
                "scale-to-zero: ignoring malformed %s (want an absolute https URL)",
                SLEEP_URL_ENV,
            )
        return None
    return url


def suspend_available(environ: Optional[dict] = None) -> bool:
    """Whether ANY suspend lever exists, in-guest or brokered.

    Quiescing without one is worse than not quiescing: the re-dial clears the flip.
    """
    env = environ if environ is not None else os.environ
    return self_suspend_available(env) or brokered_sleep_url(env) is not None


BROKERED_SUSPEND_TIMEOUT_S = 40.0

FLY_FREEZE_GRACE_S = 15.0

FLY_FREEZE_GRACE_TICK_S = 0.25


def request_brokered_suspend(
    url: str,
    *,
    timeout: float = BROKERED_SUSPEND_TIMEOUT_S,
    opener: Any = None,
) -> bool:
    """POST the Portal sleep URL so Portal stops this machine on our behalf.

    Same contract as ``suspend_self``: never raises, True only on 2xx, fail-awake.
    """
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, data=b"", method="POST")
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 0) or 0)
    except urllib.error.HTTPError as exc:
        logger.warning(
            "scale-to-zero: brokered suspend rejected: %s %s",
            exc.code,
            exc.reason,
        )
        return False
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning("scale-to-zero: brokered suspend request failed: %s", exc)
        return False
    ok = 200 <= status < 300
    if ok:
        logger.info("scale-to-zero: machine suspend accepted by Portal (%s)", status)
    else:
        logger.warning("scale-to-zero: brokered suspend returned %s", status)
    return ok


def suspend_self(environ: Optional[dict] = None, *, socket_path: str = FLY_API_SOCKET,
                 timeout: float = 10.0) -> bool:
    """POST /v1/apps/{app}/machines/{id}/suspend on the local flaps socket (the socket is the
    credential). Returns True when flaps accepted (2xx); the kernel then freezes this process
    shortly after, so treat as fire-and-forget. Never raises: a failed suspend leaves the machine
    running (fail-awake). stdlib-only on purpose — a plain unix-socket HTTP/1.1 request, no async
    plumbing to freeze mid-await."""
    app, machine_id = _env_str(environ, FLY_APP_NAME_ENV), _env_str(environ, FLY_MACHINE_ID_ENV)
    if not app or not machine_id:
        logger.warning("scale-to-zero: suspend_self called without Fly machine identity")
        return False
    request = (f"POST /v1/apps/{app}/machines/{machine_id}/suspend HTTP/1.1\r\n"
               "Host: flaps\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(socket_path)
            sock.sendall(request.encode("ascii"))
            response = b""
            while len(response) < 65536 and (chunk := sock.recv(4096)):
                response += chunk
    except OSError as exc:
        logger.warning("scale-to-zero: flaps suspend request failed: %s", exc)
        return False
    status_line = response.split(b"\r\n", 1)[0].decode("ascii", "replace")
    parts = status_line.split()
    ok = len(parts) >= 2 and parts[1].isdigit() and 200 <= int(parts[1]) < 300
    if ok:
        logger.info("scale-to-zero: machine suspend accepted by flaps (%s)", status_line)
    else:
        body = response.split(b"\r\n\r\n", 1)[-1][:500].decode("utf-8", "replace")
        logger.warning("scale-to-zero: flaps suspend rejected: %s %s", status_line,
                       json.dumps(body)[:500])
    return ok
