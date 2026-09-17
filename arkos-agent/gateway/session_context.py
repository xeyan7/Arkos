"""Session-scoped context variables for the Arkos gateway.

Replaces the old ``os.environ``-based ``ARKOS_SESSION_*`` state with task-local ``ContextVar``s
(inherited by ``run_in_executor`` threads), so concurrently handled messages no longer clobber each
other's routing ids.  ``get_session_env`` is a drop-in for ``os.getenv``.
"""

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

_UNSET: Any = object()

_session_context_engaged: bool = False


def session_context_engaged() -> bool:
    """True if any session has been bound via set_session_vars in this process."""
    return _session_context_engaged


_SESSION_VARS = (
    _SESSION_PLATFORM, _SESSION_SOURCE, _SESSION_CHAT_ID, _SESSION_CHAT_TYPE,
    _SESSION_CHAT_NAME, _SESSION_THREAD_ID, _SESSION_USER_ID, _SESSION_USER_ID_ALT,
    _SESSION_USER_NAME, _SESSION_SCOPE_ID, _SESSION_KEY, _SESSION_ID,
    _SESSION_UI_SESSION_ID, _SESSION_MESSAGE_ID, _SESSION_PROFILE,
    _BROWSER_CONTROL_PRINCIPAL, _BROWSER_CONTROL_TRANSPORT_FAMILY, _CRON_SESSION, _SESSION_PARENT_CHAT_ID,
) = tuple(ContextVar(name, default=_UNSET) for name in (
    "ARKOS_SESSION_PLATFORM", "ARKOS_SESSION_SOURCE", "ARKOS_SESSION_CHAT_ID",
    "ARKOS_SESSION_CHAT_TYPE", "ARKOS_SESSION_CHAT_NAME", "ARKOS_SESSION_THREAD_ID",
    "ARKOS_SESSION_USER_ID", "ARKOS_SESSION_USER_ID_ALT", "ARKOS_SESSION_USER_NAME",
    "ARKOS_SESSION_SCOPE_ID", "ARKOS_SESSION_KEY", "ARKOS_SESSION_ID",
    "ARKOS_UI_SESSION_ID", "ARKOS_SESSION_MESSAGE_ID", "ARKOS_SESSION_PROFILE",
    "ARKOS_BROWSER_CONTROL_PRINCIPAL", "ARKOS_BROWSER_CONTROL_TRANSPORT_FAMILY",
    "ARKOS_CRON_SESSION", "ARKOS_SESSION_PARENT_CHAT_ID",
))

_SESSION_ASYNC_DELIVERY = ContextVar("ARKOS_SESSION_ASYNC_DELIVERY", default=_UNSET)

_CRON_AUTO_DELIVER_PLATFORM = ContextVar("ARKOS_CRON_AUTO_DELIVER_PLATFORM", default=_UNSET)
_CRON_AUTO_DELIVER_CHAT_ID = ContextVar("ARKOS_CRON_AUTO_DELIVER_CHAT_ID", default=_UNSET)
_CRON_AUTO_DELIVER_THREAD_ID = ContextVar("ARKOS_CRON_AUTO_DELIVER_THREAD_ID", default=_UNSET)

_VAR_MAP = {var.name: var for var in (
    *_SESSION_VARS, _CRON_AUTO_DELIVER_PLATFORM, _CRON_AUTO_DELIVER_CHAT_ID,
    _CRON_AUTO_DELIVER_THREAD_ID,
)}


def _runtime_cwd(func: str, *args: Any) -> None:
    """Best-effort call of ``agent.runtime_cwd.<func>``; import/runtime failures are ignored."""
    try:
        from agent import runtime_cwd
        getattr(runtime_cwd, func)(*args)
    except Exception:
        pass


def set_current_session_id(session_id: str) -> None:
    """Synchronize ``ARKOS_SESSION_ID`` across ContextVar and ``os.environ`` (tools read it
    with an os.environ fallback).  Delegated subagent children (built in the parent process)
    get ONLY the task-local write, or they would clobber the parent's id."""
    _SESSION_ID.set(session_id)
    try:
        from agent.delegation_context import is_delegated_child_context
        if is_delegated_child_context():
            return
    except Exception:
        pass
    os.environ["ARKOS_SESSION_ID"] = session_id


@contextmanager
def scoped_current_session_id(session_id: str | None = None) -> Iterator[None]:
    """Bind a task-local session id and restore the prior value on exit; never touches
    ``os.environ``.  ``session_id=None`` is a pure save/restore boundary."""
    previous = _SESSION_ID.get()
    if session_id is not None:
        _SESSION_ID.set(session_id)
    try:
        yield
    finally:
        _SESSION_ID.set(previous)


def source_route_metadata(source: Any, metadata: dict | None) -> dict | None:
    """Keep inbound route anchors for durable deliveries after the source is gone."""
    anchors = {key: str(value) for key in ("scope_id", "parent_chat_id")
               if (value := getattr(source, key, None))}
    return {**(metadata or {}), **anchors} if anchors else metadata


def set_session_vars(
    platform: str = "", source: str = "", chat_id: str = "", chat_type: str = "",
    chat_name: str = "", thread_id: str = "", user_id: str = "", user_id_alt: str = "",
    user_name: str = "", scope_id: str = "", session_key: str = "", session_id: str = "",
    message_id: str = "", profile: str = "", browser_control_principal: str = "",
    browser_control_transport_family: str = "", cwd: str = "", async_delivery: bool = True,
    ui_session_id: str = "", cron_session: Any = _UNSET, parent_chat_id: str = "",
) -> list:
    """Set all session context variables and return reset tokens.  Call
    ``clear_session_vars(tokens)`` in a ``finally``; not nestable, clearing resets every var
    to ``""`` rather than restoring prior values (tokens are accepted only for API compat)."""
    global _session_context_engaged
    _session_context_engaged = True
    values = (
        platform, source, chat_id, chat_type, chat_name, thread_id, user_id, user_id_alt,
        user_name, scope_id, session_key, session_id, ui_session_id, message_id, profile,
        browser_control_principal, browser_control_transport_family, cron_session, parent_chat_id,
    )
    tokens = [var.set(value) for var, value in zip(_SESSION_VARS, values)]
    tokens.append(_SESSION_ASYNC_DELIVERY.set(bool(async_delivery)))
    _runtime_cwd("set_session_cwd", cwd)
    return tokens


def clear_session_vars(tokens: list) -> None:
    """Mark session context variables as explicitly cleared (``""``, not ``_UNSET``), so
    ``get_session_env`` returns empty instead of stale ``os.environ`` values.  Async-delivery
    goes back to ``_UNSET``: a cleared context is default-supported, not opted-out."""
    for var in _SESSION_VARS:
        var.set("")
    _SESSION_ASYNC_DELIVERY.set(_UNSET)
    _runtime_cwd("clear_session_cwd")


def reset_session_vars() -> None:
    """Reset every session var to ``_UNSET`` ("never bound here") for THIS context.  Call at
    the top of a fresh task *before* it binds: ``create_task`` snapshots the context, so B's
    task inherits A's already-set vars and a subprocess spawned before B binds would read A's
    identity.  ``_SESSION_ASYNC_DELIVERY`` (outside ``_VAR_MAP``) is reset explicitly too."""
    for var in _VAR_MAP.values():
        var.set(_UNSET)
    _SESSION_ASYNC_DELIVERY.set(_UNSET)
    _runtime_cwd("clear_session_cwd")


def get_session_env(name: str, default: str = "") -> str:
    """Read a session var by legacy ``ARKOS_SESSION_*`` name; drop-in for os.getenv.  The
    ContextVar wins if ever set here (even to ``""``); else ``os.environ``; else *default*."""
    var = _VAR_MAP.get(name)
    if var is not None and (value := var.get()) is not _UNSET:
        return value
    return os.getenv(name, default)


NON_MESSAGING_SESSION_SURFACES = frozenset({
    "", "api_server", "cli", "codex", "desktop", "gateway", "kanban", "local",
    "msgraph_webhook", "tool", "tui", "webhook",
})


def session_is_messaging_surface() -> bool:
    """Whether this turn is delivered over a human messaging channel (checks
    ``ARKOS_PLATFORM``, then the session platform, then the session source)."""
    platform = os.getenv("ARKOS_PLATFORM") or get_session_env("ARKOS_SESSION_PLATFORM", "")
    idents = (platform, get_session_env("ARKOS_SESSION_SOURCE", ""))
    idents = (str(v or "").strip().lower() for v in idents)
    return any(ident and ident not in NON_MESSAGING_SESSION_SURFACES for ident in idents)


def declare_stateless_channel() -> None:
    """Declare that this session cannot receive an async background completion.  Unlike
    ``set_session_vars(async_delivery=False)`` this does NOT latch ``_session_context_engaged``
    (flipping the subprocess env bridge), which a one-shot CLI must not do as a side effect. and .
    """
    _SESSION_ASYNC_DELIVERY.set(False)


def async_delivery_supported() -> bool:
    """Whether the current session can deliver a background completion later.  False for
    stateless channels (:func:`declare_stateless_channel`) and Kanban workers
    (``ARKOS_KANBAN_TASK``: one-shot subprocesses whose parent disappears after the turn)."""
    if os.environ.get("ARKOS_KANBAN_TASK"):
        return False
    value = _SESSION_ASYNC_DELIVERY.get()
    return True if value is _UNSET else bool(value)
