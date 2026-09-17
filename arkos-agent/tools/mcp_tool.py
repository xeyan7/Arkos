#!/usr/bin/env python3
"""MCP (Model Context Protocol) client: connects to the ``mcp_servers`` configured in
~/.arkos/config.yaml (stdio, Streamable HTTP or SSE), discovers their tools and registers them
into the arkos tool registry. The ``mcp`` package is optional (no-op without it).

One background event loop (``_mcp_loop``) in a daemon thread runs each server as a long-lived
Task (``MCPServerTask``) so the transport's anyio cancel scopes enter and exit in one Task; every
``_servers``/loop mutation holds ``_lock``. This module keeps the SDK loader, ``MCPServerTask`` and
all shared state; the ``mcp_tool_*`` siblings read that state back through ``tools.mcp_tool`` at
call time (``_core``) and are imported directly by their callers."""

import asyncio
import contextvars
import importlib
import importlib.util
import inspect
import logging
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

from tools.mcp_tool_common import _DEFAULT_TOOL_TIMEOUT, mcp_field
from tools.mcp_tool_config import _get_mcp_stderr_log, _npx_cached_bin
from tools.mcp_tool_sampling import ElicitationHandler, SamplingHandler
from tools.mcp_tool_transport import MCPServerTransportMixin
from tools.mcp_tool_server_run import MCPServerRunMixin
from tools.mcp_tool_health import MCPServerHealthMixin


_OSV_MALWARE_CHECK_TIMEOUT_S = 12.0


async def _preflight_stdio_command(server_name: str, command: str, args: list) -> tuple[str, list]:
    """OSV malware preflight (off-loop, wall-clock bound, fail-open on timeout), THEN the
    cached-npx swap. The preflight must see the REAL command/args: anything that rewrites argv to a
    wrapper or resolved binary has to happen after it, or the check silently inspects the wrapper
    and becomes a no-op (``_infer_ecosystem`` keys off the command basename being npx/uvx/pipx)."""
    from tools.osv_check import check_package_for_malware
    try:
        malware_error = await asyncio.wait_for(
            asyncio.to_thread(check_package_for_malware, command, args), timeout=_OSV_MALWARE_CHECK_TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning("MCP server '%s': OSV malware preflight timed out after %.0fs "
                       "(network slow/unreachable) — proceeding without the check.",
                       server_name, _OSV_MALWARE_CHECK_TIMEOUT_S)
        malware_error = None
    if malware_error:
        raise ValueError(f"MCP server '{server_name}': {malware_error}")

    if os.path.basename(command).lower().startswith("npx"):
        cached = _npx_cached_bin(args)
        if cached:
            direct_command, direct_args = cached
            logger.debug("MCP server '%s': using cached npx binary %s (skipping the "
                         "resident `npm exec` parent)", server_name, direct_command)
            command, args = direct_command, direct_args
    return command, args



_MCP_AVAILABLE = _MCP_HTTP_AVAILABLE = _MCP_NEW_HTTP = _MCP_LEGACY_HTTP = False
_MCP_SAMPLING_TYPES = _MCP_NOTIFICATION_TYPES = _MCP_ELICITATION_TYPES = False
_MCP_MESSAGE_HANDLER_SUPPORTED = _MCP_LOGGING_CALLBACK_SUPPORTED = False
sse_client = None
LATEST_PROTOCOL_VERSION = "2025-03-26"
LATEST_HANDSHAKE_VERSION = LATEST_PROTOCOL_VERSION

try:
    _MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None
except Exception:
    _MCP_AVAILABLE = False
if not _MCP_AVAILABLE:
    logger.debug("mcp package not installed -- MCP tool support disabled")

ClientSession: Any = None
_MCP_SDK_IMPORT_ATTEMPTED = False
_MCP_SDK_IMPORT_LOCK = threading.Lock()

_OPTIONAL_TYPE_FAMILIES = (
    ("mcp.types", ("CreateMessageResult", "CreateMessageResultWithTools", "ErrorData", "SamplingCapability",
                   "SamplingToolsCapability", "TextContent", "ToolUseContent"),
     "MCP sampling types not available -- sampling disabled"),
    ("mcp.types", ("ElicitRequestParams", "ElicitResult"),
     "MCP elicitation types not available -- elicitation disabled"),
    ("mcp.types", ("ServerNotification", "ToolListChangedNotification", "PromptListChangedNotification",
                   "ResourceListChangedNotification"),
     "MCP notification types not available -- dynamic tool discovery disabled"),
)
_MCP_SDK_LAZY_SYMBOLS = frozenset(
    {"StdioServerParameters", "stdio_client", "streamablehttp_client", "streamable_http_client"}
    | {n for _mod, names, _msg in _OPTIONAL_TYPE_FAMILIES for n in names})


def __getattr__(name: str):
    if name in _MCP_SDK_LAZY_SYMBOLS:
        _ensure_mcp_sdk()
        try:
            return globals()[name]
        except KeyError:
            pass
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _import_sdk_names(module: str, names: tuple, missing_msg: Optional[str] = None) -> bool:
    """Bind ``names`` from SDK ``module`` into this module's globals; False (nothing bound,
    optional debug line) when this SDK build lacks the module or any of the names."""
    try:
        mod = importlib.import_module(module)
        values = {n: getattr(mod, n) for n in names}
    except (ImportError, AttributeError):
        if missing_msg:
            logger.debug(missing_msg)
        return False
    globals().update(values)
    return True


def _ensure_mcp_sdk() -> bool:
    """Import the optional ``mcp`` SDK on first use; return availability. Idempotent and
    thread-safe; honors a test-patched ``_MCP_AVAILABLE=False`` (no import) and pre-installed
    mocks (``ClientSession`` already set means no re-import)."""
    global _MCP_SDK_IMPORT_ATTEMPTED, _MCP_AVAILABLE, _MCP_HTTP_AVAILABLE, _MCP_NEW_HTTP, _MCP_LEGACY_HTTP
    global _MCP_SAMPLING_TYPES, _MCP_NOTIFICATION_TYPES, _MCP_ELICITATION_TYPES, sse_client
    global _MCP_MESSAGE_HANDLER_SUPPORTED, _MCP_LOGGING_CALLBACK_SUPPORTED, LATEST_HANDSHAKE_VERSION
    global _JSONRPC_METHOD_NOT_FOUND
    if not _MCP_AVAILABLE:
        return False
    if _MCP_SDK_IMPORT_ATTEMPTED or ClientSession is not None:
        return _MCP_AVAILABLE
    with _MCP_SDK_IMPORT_LOCK:
        if _MCP_SDK_IMPORT_ATTEMPTED or ClientSession is not None:
            return _MCP_AVAILABLE
        if (_import_sdk_names("mcp", ("ClientSession", "StdioServerParameters"))
                and _import_sdk_names("mcp.client.stdio", ("stdio_client",))):
            _MCP_AVAILABLE = True
            _MCP_NEW_HTTP = _import_sdk_names("mcp.client.streamable_http", ("streamable_http_client",))
            _MCP_LEGACY_HTTP = _import_sdk_names("mcp.client.streamable_http", ("streamablehttp_client",))
            _MCP_HTTP_AVAILABLE = _MCP_NEW_HTTP or _MCP_LEGACY_HTTP
            _import_sdk_names("mcp.types", ("LATEST_PROTOCOL_VERSION",),
                              "mcp.types.LATEST_PROTOCOL_VERSION not available -- using fallback protocol version")
            if not _import_sdk_names("mcp.client.session", ("LATEST_HANDSHAKE_VERSION",)):
                LATEST_HANDSHAKE_VERSION = LATEST_PROTOCOL_VERSION
            if not _import_sdk_names("mcp.client.sse", ("sse_client",),
                                     "mcp.client.sse.sse_client not available -- SSE transport disabled"):
                sse_client = None
            _MCP_SAMPLING_TYPES, _MCP_ELICITATION_TYPES, _MCP_NOTIFICATION_TYPES = [
                _import_sdk_names(*family) for family in _OPTIONAL_TYPE_FAMILIES]
        else:
            logger.debug("mcp package not installed -- MCP tool support disabled")
        if _MCP_AVAILABLE:
            try:
                _JSONRPC_METHOD_NOT_FOUND = importlib.import_module("mcp.types").METHOD_NOT_FOUND
            except Exception:  # pragma: no cover — SDK without the constant
                pass
        _MCP_MESSAGE_HANDLER_SUPPORTED = _client_session_accepts("message_handler")
        if _MCP_AVAILABLE and not _MCP_MESSAGE_HANDLER_SUPPORTED:
            logger.debug("MCP SDK does not support message_handler -- dynamic tool discovery disabled")
        _MCP_LOGGING_CALLBACK_SUPPORTED = _client_session_accepts("logging_callback")
        _MCP_SDK_IMPORT_ATTEMPTED = True
        return _MCP_AVAILABLE


_SDK_HTTPX_MOD = None


def sdk_httpx():
    """The httpx module the *installed* MCP SDK is built against (mcp 2.0 moved to ``httpx2``).
    Every object crossing the SDK boundary (AsyncClient, OAuth Request, exception classes) must
    come from the module the SDK itself imports or it fails at the transport layer. Resolved
    from the SDK's transport module, else the newest present; ``None`` if neither imports."""
    global _SDK_HTTPX_MOD
    if _SDK_HTTPX_MOD is not None:
        return _SDK_HTTPX_MOD
    try:
        from mcp.client import streamable_http as _transport
        _SDK_HTTPX_MOD = getattr(_transport, "httpx2", None) or getattr(_transport, "httpx", None)
    except ImportError:
        _SDK_HTTPX_MOD = None
    for fallback in ("httpx2", "httpx"):
        if _SDK_HTTPX_MOD is not None:
            break
        try:
            _SDK_HTTPX_MOD = importlib.import_module(fallback)
        except ImportError:
            pass
    return _SDK_HTTPX_MOD


def _client_session_accepts(kwarg: str) -> bool:
    """Whether this SDK's ``ClientSession.__init__`` takes ``kwarg`` (older SDKs lack
    ``message_handler`` and ``logging_callback``)."""
    if not _MCP_AVAILABLE:
        return False
    try:
        return kwarg in inspect.signature(ClientSession).parameters
    except (TypeError, ValueError):
        return False


_MCP_LOG_LEVEL_MAP = {
    "debug": logging.DEBUG, "info": logging.INFO, "notice": logging.INFO,
    "warning": logging.WARNING, "error": logging.ERROR, "critical": logging.ERROR,
    "alert": logging.ERROR, "emergency": logging.ERROR}


_DEFAULT_CONNECT_TIMEOUT = 60
_MAX_RECONNECT_RETRIES = 5
_MAX_INITIAL_CONNECT_RETRIES = 3
_MAX_BACKOFF_SECONDS = 60
_RECYCLED_RECONNECT_TIMEOUT = 15.0
_PARKED_RETRY_INTERVAL = 300
_STDIO_RESPAWN_WAIT_SEC = 15.0
_DEFAULT_KEEPALIVE_INTERVAL, _MIN_KEEPALIVE_INTERVAL = 180, 5
_MCP_LOOP_DRAIN_TIMEOUT = 3.0
_JSONRPC_METHOD_NOT_FOUND = -32601
_MCP_LIST_MAX_PAGES = 50


async def _paginate_full_list(list_method, items_attr: str, server_name: str,
                              cache_meta_out: Optional[dict] = None):
    """Drain a paginated ``list_*`` call by following ``nextCursor``; ``cache_meta_out`` gets the
    first page's SEP-2549 hints. Callers must hold the server's ``_rpc_lock``."""
    items: list = []
    cursor = None
    for _ in range(_MCP_LIST_MAX_PAGES):
        if not cursor:
            result = await list_method()
        else:
            import inspect

            try:
                signature = inspect.signature(list_method)
            except (TypeError, ValueError):
                accepts_params = True
            else:
                accepts_params = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD
                    or (p.name == "params" and p.kind != inspect.Parameter.POSITIONAL_ONLY)
                    for p in signature.parameters.values()
                )
            if accepts_params:
                import mcp.types as _types
                _params_cls = getattr(_types, "PaginatedRequestParams", None)
                if _params_cls is not None:
                    result = await list_method(params=_params_cls(cursor=cursor))
                else:
                    result = await list_method(cursor=cursor)
            else:
                result = await list_method(cursor=cursor)
        if cache_meta_out is not None and not items:
            for key, snake, camel in (("ttl_ms", "ttl_ms", "ttlMs"), ("cache_scope", "cache_scope", "cacheScope")):
                hint = mcp_field(result, snake, camel)
                if hint is not None:
                    cache_meta_out[key] = hint
        items.extend(getattr(result, items_attr, None) or [])
        cursor = mcp_field(result, "next_cursor", "nextCursor")
        if not isinstance(cursor, str) or not cursor:
            break
    else:
        logger.warning("MCP server '%s': %s pagination exceeded %d pages; truncating at %d items",
                       server_name, items_attr, _MCP_LIST_MAX_PAGES, len(items))
    return items



class MCPServerTask(MCPServerRunMixin, MCPServerTransportMixin, MCPServerHealthMixin):
    """One MCP server connection in one long-lived asyncio Task (the transport's anyio cancel
    scopes must enter/exit in the same Task). Run state machine, transport bring-up and
    keepalive/liveness live in the three mixins."""

    __slots__ = (
        "name", "session", "tool_timeout", "_task", "_ready", "_shutdown_event", "_reconnect_event",
        "_tools", "_error", "_config", "_sampling", "_elicitation", "_registered_tool_names",
        "_auth_type", "_refresh_lock", "_rpc_lock", "_pending_refresh_tasks", "_pending_call_context",
        "_lifecycle_started_at", "_last_tool_call_at", "_idle_timeout_seconds", "_max_lifetime_seconds",
        "_recycled_reason", "initialize_result", "_ping_unsupported", "_list_cache_meta",
        "_reconnect_retries", "_session_proven", "_was_parked", "_inflight_tasks", "_reconnecting",
        "_suspect_reason", "_teardown_race", "_permanent_grace_used", "_stdio_child_pids",
        "_ever_connected")

    def __init__(self, name: str):
        self.name = name
        self.session: Optional[Any] = None
        self.tool_timeout: float = _DEFAULT_TOOL_TIMEOUT
        self._task: Optional[asyncio.Task] = None
        self._ready = asyncio.Event()
        self._shutdown_event = asyncio.Event()
        self._reconnect_event = asyncio.Event()
        self._tools: list = []
        self._registered_tool_names: list[str] = []
        self._config: dict = {}
        self._error: Optional[Exception] = None
        self._sampling: Optional[SamplingHandler] = None
        self._elicitation: Optional[ElicitationHandler] = None
        self._reconnect_retries: int = 0
        self._session_proven: bool = False
        self._ever_connected: bool = False
        self._was_parked: bool = False
        self._inflight_tasks: set = set()
        self._reconnecting: bool = False
        self._suspect_reason: Optional[str] = None
        self._teardown_race: bool = False
        self._permanent_grace_used: bool = False
        self._stdio_child_pids: Set[int] = set()
        self._auth_type: str = ""
        self._refresh_lock = asyncio.Lock()
        self._rpc_lock = asyncio.Lock()
        self._pending_refresh_tasks: set[asyncio.Task] = set()
        self._pending_call_context: Optional[contextvars.Context] = None
        self._lifecycle_started_at = self._last_tool_call_at = time.monotonic()
        self._idle_timeout_seconds = self._max_lifetime_seconds = self._recycled_reason = None
        self.initialize_result: Optional[Any] = None
        self._list_cache_meta: dict = {}
        self._ping_unsupported: bool = False

    _MCP_CONTENT_TYPES = ("application/json", "text/event-stream")



_servers: Dict[str, MCPServerTask] = {}
_server_scope_keys: Dict[str, Optional[str]] = {}
_server_connecting: set[str] = set()
_server_connect_errors: Dict[str, str] = {}
_lazy_server_configs: Dict[str, dict] = {}
_lazy_server_fingerprints: Dict[str, str] = {}
_lazy_server_tool_names: Dict[str, List[str]] = {}
_connect_server_claim: contextvars.ContextVar[Optional[Callable[[MCPServerTask], None]]] = (
    contextvars.ContextVar("mcp_connect_server_claim", default=None))

_server_connect_retry_after: Dict[str, float] = {}
_server_connect_failures: Dict[str, int] = {}
_CONNECT_RETRY_BASE_BACKOFF_SEC, _CONNECT_RETRY_MAX_BACKOFF_SEC = 30.0, 600.0

_server_error_counts: Dict[str, int] = {}
_server_breaker_opened_at: Dict[str, float] = {}
_CIRCUIT_BREAKER_THRESHOLD, _CIRCUIT_BREAKER_COOLDOWN_SEC = 3, 60.0

_server_trust_levels: Dict[str, str] = {}
_tool_read_only_hints: Dict[str, Dict[str, bool]] = {}

_TRUST_FULL, _TRUST_UNTRUSTED = "full", "untrusted"


def _bump_server_error(server_name: str) -> None:
    """Count a failure; at the threshold (re)stamp the breaker-open time."""
    n = _server_error_counts.get(server_name, 0) + 1
    _server_error_counts[server_name] = n
    if n >= _CIRCUIT_BREAKER_THRESHOLD:
        _server_breaker_opened_at[server_name] = time.monotonic()


def _reset_server_error(server_name: str) -> None:
    """Close the breaker on any unambiguous success signal."""
    _server_error_counts[server_name] = 0
    _server_breaker_opened_at.pop(server_name, None)


_parallel_safe_servers: set = set()
_mcp_tool_server_names: Dict[str, str] = {}

_mcp_loop: Optional[asyncio.AbstractEventLoop] = None
_mcp_thread: Optional[threading.Thread] = None
_lock = threading.Lock()


_death_supervisor = None
_death_supervisor_lock = threading.Lock()
_supervised_pgids: set = set()


def _spawn_death_supervisor():
    """Start the shared supervisor, or None if it cannot be started."""
    import subprocess
    supervisor = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_death_supervisor.py")
    try:
        return subprocess.Popen(
            [sys.executable, supervisor, "--parent-pgid", str(os.getpgid(0))],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=_get_mcp_stderr_log(),
            start_new_session=True, close_fds=True, text=True)
    except Exception:
        logger.debug("Could not start the MCP parent-death supervisor", exc_info=True)
        return None


def _prune_dead_supervised_pgids() -> set:
    """Forget supervised groups with no members left; return what went. Caller holds
    ``_death_supervisor_lock``. Signal 0 is a pure existence probe (cannot terminate anything).
    It narrows, but cannot close, the window where a dead group's pgid is recycled before we
    notice (residual-risk note in ``tools/mcp_death_supervisor.py``)."""
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        return set()
    stale = set()
    for pgid in list(_supervised_pgids):
        try:
            killpg(pgid, 0)
        except ProcessLookupError:
            stale.add(pgid)
        except (PermissionError, OSError):
            pass
    _supervised_pgids.difference_update(stale)
    return stale


def _update_death_supervisor(verb: str, pgids) -> None:
    """Register or unregister process groups (``verb`` is ``"register"``/``"unregister"``) with
    the shared supervisor. Failures are swallowed: losing the safety net must never fail a live
    MCP session."""
    if os.name != "posix":
        return
    wanted = {int(pgid) for pgid in pgids}
    if not wanted:
        return

    global _death_supervisor
    with _death_supervisor_lock:
        if verb == "register":
            _supervised_pgids.update(wanted)
        else:
            _supervised_pgids.difference_update(wanted)

        stale = _prune_dead_supervised_pgids()

        proc = _death_supervisor
        if proc is None or proc.poll() is not None:
            if not _supervised_pgids:
                return
            proc = _spawn_death_supervisor()
            _death_supervisor = proc
            if proc is None:
                return
            payload = "".join(f"register {pgid}\n" for pgid in _supervised_pgids)
        else:
            payload = "".join(f"{verb} {pgid}\n" for pgid in wanted)
            payload += "".join(f"unregister {pgid}\n" for pgid in stale)

        try:
            proc.stdin.write(payload)
            proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError):
            _death_supervisor = None
            return

        if not _supervised_pgids:
            try:
                proc.stdin.close()
            except (BrokenPipeError, ValueError, OSError):
                pass
            try:
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001 - timeout or already gone; either way we drop it
                pass
            _death_supervisor = None


def _mcp_registry_scope() -> Optional[str]:
    """Registry scope for MCP registrations: a profile overlay under a multiplexer, else None."""
    from agent.secret_scope import is_multiplex_active
    if not is_multiplex_active():
        return None
    from tools.registry import registry
    return registry.current_scope_key()


def _server_registry_scope(name: str) -> Optional[str]:
    """Scope owning *name*'s tools: the one captured at adoption (teardown runs on the MCP
    loop without the discovering profile's context), else the current one."""
    if name in _server_scope_keys:
        return _server_scope_keys[name]
    return _mcp_registry_scope()


_LOCK_UNAVAILABLE: Any = object()
_MCP_DISCOVERY_LOCK_PATH: Optional[str] = None
_MCP_DISCOVERY_LOCK_MAX_RETRIES, _MCP_DISCOVERY_LOCK_RETRY_DELAY_S = 240, 0.5


from typing import Coroutine  # noqa: F401,E402
from types import SimpleNamespace  # noqa: F401,E402
from typing import Tuple  # noqa: F401,E402
from contextlib import asynccontextmanager  # noqa: F401,E402
import concurrent.futures  # noqa: F401,E402
from datetime import datetime  # noqa: F401,E402
import errno  # noqa: F401,E402
import fnmatch  # noqa: F401,E402
import json  # noqa: F401,E402
import math  # noqa: F401,E402
import random  # noqa: F401,E402
import re  # noqa: F401,E402
import shutil  # noqa: F401,E402
from urllib.parse import urlparse  # noqa: F401,E402


_PLUGIN_COMPAT_LAZY = {
    'InvalidMcpUrlError': ('tools.mcp_tool_errors', 'InvalidMcpUrlError'),
    'MCP_TOOL_NAME_PREFIX': ('tools.mcp_tool_schema', 'MCP_TOOL_NAME_PREFIX'),
    'NonMcpEndpointError': ('tools.mcp_tool_errors', 'NonMcpEndpointError'),
    'discover_mcp_tools': ('tools.mcp_tool_discovery', 'discover_mcp_tools'),
    'get_mcp_status': ('tools.mcp_tool_discovery', 'get_mcp_status'),
    'get_registered_mcp_server_names': ('tools.mcp_tool_discovery', 'get_registered_mcp_server_names'),
    'has_registered_mcp_tools': ('tools.mcp_tool_discovery', 'has_registered_mcp_tools'),
    'is_mcp_tool_parallel_safe': ('tools.mcp_tool_discovery', 'is_mcp_tool_parallel_safe'),
    'matches_name_filter': ('tools.mcp_tool_schema', 'matches_name_filter'),
    'mcp_prefixed_tool_name': ('tools.mcp_tool_schema', 'mcp_prefixed_tool_name'),
    'persist_agent_tool_names': ('tools.mcp_tool_agent', 'persist_agent_tool_names'),
    'probe_mcp_server_tools': ('tools.mcp_tool_discovery', 'probe_mcp_server_tools'),
    'reconnect_mcp_server': ('tools.mcp_tool_loop', 'reconnect_mcp_server'),
    'refresh_agent_mcp_tools': ('tools.mcp_tool_agent', 'refresh_agent_mcp_tools'),
    'register_mcp_servers': ('tools.mcp_tool_discovery', 'register_mcp_servers'),
    'reprobe_tool_availability': ('tools.mcp_tool_agent', 'reprobe_tool_availability'),
    'restore_agent_tool_prefix': ('tools.mcp_tool_agent', 'restore_agent_tool_prefix'),
    'sanitize_mcp_name_component': ('tools.mcp_tool_schema', 'sanitize_mcp_name_component'),
    'shutdown_mcp_servers': ('tools.mcp_tool_lifecycle', 'shutdown_mcp_servers'),
    'strip_unicode_tags': ('tools.ansi_strip', 'strip_unicode_tags'),
    'tool_error': ('tools.registry', 'tool_error'),
}

_plugin_compat_prev_getattr = __getattr__


def __getattr__(name):
    target = _PLUGIN_COMPAT_LAZY.get(name)
    if target is None:
        return _plugin_compat_prev_getattr(name)
    import importlib
    from arkos_cli.plugin_compat import warn_once
    warn_once(__name__, name, *target)
    return getattr(importlib.import_module(target[0]), target[1])
