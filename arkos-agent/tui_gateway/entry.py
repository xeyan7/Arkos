import os
import sys

import arkos_bootstrap

arkos_bootstrap.harden_import_path()

import json
import logging
import signal
import threading
import time
import traceback
from contextlib import suppress

from tui_gateway._env import env_float
from tui_gateway._stdin_recovery import handle_spurious_eof

from tui_gateway import server
from tui_gateway.event_replay import replay_epoch
from tui_gateway.server import _CRASH_LOG, dispatch, resolve_skin, write_json
from tui_gateway.transport import TeeTransport

logger = logging.getLogger(__name__)

_mcp_discovery_thread = None
_mcp_discovery_enabled = False


def _install_sidecar_publisher() -> None:
    """Mirror every dispatcher emit to the dashboard sidebar via WS when set (best-effort)."""
    url = os.environ.get("ARKOS_TUI_SIDECAR_URL")
    if not url:
        return
    from tui_gateway.event_publisher import WsPublisherTransport
    server._stdio_transport = TeeTransport(server._stdio_transport, WsPublisherTransport(url))


_DEFAULT_SHUTDOWN_GRACE_S = 1.0


def _shutdown_grace_seconds() -> float:
    value = env_float("ARKOS_TUI_GATEWAY_SHUTDOWN_GRACE_S", _DEFAULT_SHUTDOWN_GRACE_S)
    return value if value > 0 else _DEFAULT_SHUTDOWN_GRACE_S


def _mcp_startup_call(name: str, *args, default=None, log=None, **kwargs):
    """Call ``arkos_cli.mcp_startup.<name>`` (lazy import); ``default`` on any failure,
    optionally logged as ``(level, message)``."""
    try:
        from arkos_cli import mcp_startup
        return getattr(mcp_startup, name)(*args, **kwargs)
    except Exception:
        if log:
            getattr(logger, log[0])(log[1], exc_info=True)
        return default


def _spawn_discovery(log: tuple) -> None:
    _mcp_startup_call(
        "start_background_mcp_discovery", logger=logger, thread_name="tui-mcp-discovery", log=log)


def _append_crash_log(header: str, dump=None) -> None:
    """Best-effort ``=== header ===`` entry in the crash log; ``dump(f)`` adds detail."""
    with suppress(Exception):
        os.makedirs(os.path.dirname(_CRASH_LOG), exist_ok=True)
        with open(_CRASH_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n=== {header} ===\n")
            if dump is not None:
                dump(f)


def _log_signal(signum: int, frame) -> None:
    """Capture WHICH thread and WHERE a termination signal hit us, then exit. ``sys.exit(0)``
    alone raced the worker pool (a thread holding ``_stdout_lock`` mid-flush blocks interpreter
    shutdown), so: log all thread stacks, give the configured grace to drain, then ``os._exit``."""
    names = {int(sig): attr for attr in ("SIGPIPE", "SIGTERM", "SIGHUP", "SIGINT", "SIGBREAK")
             if (sig := getattr(signal, attr, None)) is not None}
    name = names.get(signum, f"signal {signum}")

    def _dump(f):
        if frame is not None:
            f.write("main-thread stack at signal delivery:\n")
            traceback.print_stack(frame, file=f)
        for tid, th in threading._active.items():
            f.write(f"\n--- thread {th.name} (id={tid}) ---\n")
            f.write("".join(traceback.format_stack(sys._current_frames().get(tid))))

    _append_crash_log(f"{name} received · {time.strftime('%Y-%m-%d %H:%M:%S')}", _dump)
    print(f"[gateway-signal] {name}", file=sys.stderr, flush=True)
    timer = threading.Timer(_shutdown_grace_seconds(), lambda: os._exit(0))
    timer.daemon = True
    timer.start()
    with suppress(Exception):
        from tui_gateway.server import _shutdown_sessions
        _shutdown_sessions()
    sys.exit(0)


def _install_signal(signame, handler):
    """Install a signal handler if legal here: signal.signal() raises off the main thread
    (Desktop build path imports entry from a worker) and Windows lacks SIGPIPE/SIGHUP."""
    sig = getattr(signal, signame, None)
    if sig is None or threading.current_thread() is not threading.main_thread():
        return
    with suppress(ValueError, OSError, RuntimeError):
        signal.signal(sig, handler)


_install_signal("SIGPIPE", signal.SIG_IGN)
_install_signal("SIGTERM", _log_signal)
if hasattr(signal, "SIGHUP"):
    _install_signal("SIGHUP", _log_signal)
elif hasattr(signal, "SIGBREAK"):
    _install_signal("SIGBREAK", _log_signal)
_install_signal("SIGINT", signal.SIG_IGN)


def _log_exit(reason: str) -> None:
    """Record why the gateway exits (every path is a silent sys.exit(0) otherwise)."""
    _append_crash_log(f"gateway exit · {time.strftime('%Y-%m-%d %H:%M:%S')} · reason={reason}")
    print(f"[gateway-exit] {reason}", file=sys.stderr, flush=True)


def wait_for_mcp_discovery(timeout: "float | None" = None) -> None:
    """Block until background MCP discovery finishes, up to the resolved bound (config
    ``mcp_discovery_timeout``; ``timeout`` overrides). The agent snapshots its tool list ONCE
    at build time, so this bounded join lets already-spawning servers land."""
    thread = _mcp_discovery_thread
    if thread is not None and thread.is_alive():
        fallback = timeout if timeout is not None else 0.75
        bound = _mcp_startup_call("_resolve_discovery_timeout", timeout, default=fallback)
        thread.join(timeout=bound)
        return
    if not _mcp_discovery_enabled:
        return
    _spawn_discovery(("debug", "TUI MCP discovery retry-spawn failed"))
    _mcp_startup_call("wait_for_mcp_discovery", timeout)


def mcp_discovery_in_flight() -> bool:
    """True if ANY background MCP discovery thread is still running: the late-refresh
    scheduler calls this regardless of surface, so it MUST consult both owners.

    There are two independent discovery-thread owners by surface: the stdio ``arkos --tui`` path spawns ITS
    thread here (``_mcp_discovery_thread``), while the desktop app + dashboard WebSocket sidecar
    (``tui_gateway/ws.py``) and ``arkos dashboard`` spawn theirs via
    ``arkos_cli.mcp_startup.start_background_mcp_discovery``. The late-refresh scheduler imports this
    function regardless of surface, so it MUST consult both — checking only the entry thread left the
    desktop/dashboard surfaces with no late refresh, so a slow MCP server's tools never surfaced for the
    whole session.
    """
    thread = _mcp_discovery_thread
    if thread is not None and thread.is_alive():
        return True
    return _mcp_startup_call("mcp_discovery_in_flight", default=False)


def join_mcp_discovery(timeout: float | None = None) -> bool:
    """Join both discovery owners; True once neither is alive. Accepts an unbounded wait
    (off-critical-path late-refresh waiter); ``timeout`` bounds EACH join, entry thread first.

    Joins both discovery-thread owners (see ``mcp_discovery_in_flight``): the entry thread first, then the
    ``arkos_cli.mcp_startup`` thread used by the desktop/dashboard surfaces..
    """
    entry_done = True
    thread = _mcp_discovery_thread
    if thread is not None:
        thread.join(timeout=timeout)
        entry_done = not thread.is_alive()
    return entry_done and _mcp_startup_call("join_mcp_discovery", timeout=timeout, default=True)


_recovery_times: list[float] = []


def _has_configured_mcp_servers() -> bool:
    """Delegate to the shared native and portable MCP startup gate."""
    from arkos_cli.mcp_startup import _has_configured_mcp_servers as configured
    return configured()


def ensure_mcp_discovery_started() -> None:
    """Start background MCP discovery for the current profile context, once. ``main`` calls
    this for stdio; ``server._start_agent_build`` also calls it AFTER binding the session
    profile's ARKOS_HOME. MCP registration is process-global: the FIRST profile wins.

    WebSocket/Desktop entrypoints can accept sessions without running ``main``, so the agent-build path
    (``server._start_agent_build``) also calls it AFTER binding the session profile's ARKOS_HOME override —
    the shared owner in ``arkos_cli.mcp_startup`` captures the caller's context-local override and
    propagates it into the discovery thread, so discovery reads the SELECTED profile's ``mcp_servers``, not
    the launch profile's.
    Known limitation: MCP tool registration is process-global, so in a multi-profile process the FIRST
    profile that builds an agent wins the discovery slot. Full per-profile MCP registries are tracked in
    .
    """
    global _mcp_discovery_enabled
    if not _has_configured_mcp_servers():
        return
    _mcp_discovery_enabled = True
    _spawn_discovery(("warning", "Background MCP tool discovery failed to start"))


def _write_or_exit(payload: dict, reason: str) -> None:
    if not write_json(payload):
        _log_exit(reason)
        sys.exit(0)


def main():
    _install_sidecar_publisher()

    for start, what in (
            (server._start_backend_heartbeat_refresher, "backend heartbeat refresher start"),
            (server._schedule_startup_orphan_sweep, "startup orphan sweep scheduling")):
        try:
            start()
        except Exception:
            logger.warning("%s failed", what, exc_info=True)

    ensure_mcp_discovery_started()

    _write_or_exit({
        "jsonrpc": "2.0", "method": "event",
        "params": {"type": "gateway.ready", "payload": {
            "skin": resolve_skin(), "change_events": True, "replay_epoch": replay_epoch()}}},
        "startup write failed (broken stdout pipe before first event)")

    server._ensure_skin_watcher()

    try:
        from arkos_cli.model_switch_providers import prewarm_picker_cache_async
        prewarm_picker_cache_async()
    except Exception:
        logger.debug("picker cache prewarm (tui) failed to start", exc_info=True)

    while True:
        raw = sys.stdin.readline()
        if not raw:
            if not handle_spurious_eof(_recovery_times, _log_exit):
                break
            continue
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            _write_or_exit(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": "parse error"}, "id": None},
                "parse-error-response write failed (broken stdout pipe)")
            continue

        method = req.get("method") if isinstance(req, dict) else None
        resp = dispatch(req)
        if resp is not None:
            _write_or_exit(
                resp, f"response write failed for method={method!r} (broken stdout pipe)")


if __name__ == "__main__":
    main()
