"""WebSocket transport for the tui_gateway JSON-RPC server: reuses :func:`tui_gateway.server.dispatch`
verbatim so every RPC, slash command, approval flow and agent event takes the same handlers as Ink over
stdio. Wire protocol is identical to stdio (newline-delimited JSON-RPC both ways; ``gateway.ready`` right
after accept). Mount as ``@app.websocket("/api/ws") async def ws(ws): await handle_ws(ws)``."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import socket
import threading
import time
from typing import Any

from tui_gateway import server
from agent.message_sanitization import _sanitize_surrogates
from tui_gateway.event_replay import replay_epoch

_log = logging.getLogger(__name__)

_DASHBOARD_CLIENT_TOUCH_MIN_INTERVAL_S = 5.0
_dashboard_client_touched_at = 0.0
_dashboard_client_touch_lock = threading.Lock()


def _note_dashboard_client_activity(*, force: bool = False) -> None:
    """Refresh the dashboard-client liveness marker (throttled, best-effort)."""
    global _dashboard_client_touched_at
    now = time.monotonic()
    with _dashboard_client_touch_lock:
        if not force and now - _dashboard_client_touched_at < _DASHBOARD_CLIENT_TOUCH_MIN_INTERVAL_S:
            return
        _dashboard_client_touched_at = now
    try:
        from gateway.scale_to_zero import touch_dashboard_client_heartbeat
        touch_dashboard_client_heartbeat()
    except Exception:  # noqa: BLE001 - liveness garnish must never break the WS
        _log.debug("dashboard client heartbeat touch failed", exc_info=True)


def _sanitize_ws_text(text: str) -> str:
    """Return *text* that can be UTF-8 encoded for a WebSocket frame.

    ``json.dumps(..., ensure_ascii=False)`` happily emits lone UTF-16 surrogates; Starlette's
    ``send_text`` then raises ``UnicodeEncodeError``, which used to latch the whole connection
    closed. Same U+FFFD replacement every other Arkos transport applies..
    """
    return _sanitize_surrogates(text) if text else text


_WS_WRITE_TIMEOUT_S = 10.0
_WS_LOG_PAYLOAD_PREVIEW = 240

_STREAMING_EVENT_TYPES = frozenset({"message.delta", "reasoning.delta", "thinking.delta"})
_TOKEN_COALESCE_S = 0.033

try:
    from starlette.websockets import WebSocketDisconnect as _WebSocketDisconnect
except ImportError:  # pragma: no cover - starlette is a required install path
    _WebSocketDisconnect = Exception  # type: ignore[assignment]


class WSTransport:
    """Per-connection WS transport. ``write`` is safe from any thread *other than* the loop thread owning the
    socket (pool workers marshal onto the loop and block on the future); from the loop thread itself it would
    deadlock, so it detects that and fires-and-forgets. Loop-thread callers needing completion use ``write_async``."""

    def __init__(self, ws: Any, loop: asyncio.AbstractEventLoop, *, peer: str = "unknown",
                 auth_identity: dict | None = None) -> None:
        self._ws = ws
        self._loop = loop
        self._peer = peer
        self.auth_identity = auth_identity
        self._closed = False
        self._token_lock = threading.Lock()
        self._pending_tokens: list[str] = []
        self._token_flush_handle: asyncio.TimerHandle | None = None
        self._token_flush_armed = False
        self._send_lock = asyncio.Lock()

    def write(self, obj: dict) -> bool:
        if self._closed:
            return False
        line = json.dumps(obj, ensure_ascii=False)
        try:
            on_loop = asyncio.get_running_loop() is self._loop
        except RuntimeError:
            on_loop = False
        params = obj.get("params") if isinstance(obj, dict) else None
        if isinstance(params, dict) and params.get("type") in _STREAMING_EVENT_TYPES:
            with self._token_lock:
                self._pending_tokens.append(line)
                if not self._token_flush_armed:
                    self._token_flush_armed = True
                    self._loop.call_soon_threadsafe(self._arm_token_flush)
            return not self._closed
        from agent.async_utils import safe_schedule_threadsafe
        with self._token_lock:
            self._pending_tokens.append(line)
            batch, self._pending_tokens = self._pending_tokens, []
            if on_loop:
                self._loop.create_task(self._safe_send_many(batch))
                return True
            fut = safe_schedule_threadsafe(self._safe_send_many(batch), self._loop)
            if fut is None:
                self._closed = True
                return False
        try:
            fut.result(timeout=_WS_WRITE_TIMEOUT_S)
            return not self._closed
        except concurrent.futures.TimeoutError:
            _log.warning("ws write slow (loop stalled >%ss) peer=%s — frame left in flight", _WS_WRITE_TIMEOUT_S, self._peer)
            return not self._closed
        except Exception as exc:
            self._closed = True
            _log.warning("ws write failed peer=%s error_type=%s error=%s", self._peer, type(exc).__name__, exc)
            return False

    def _arm_token_flush(self) -> None:
        if not self._closed:
            self._token_flush_handle = self._loop.call_later(_TOKEN_COALESCE_S, self._flush_tokens)

    def _flush_tokens(self) -> None:
        """Timer callback (loop thread): send buffered tokens as one batch, scheduled under the lock so
        wire order is fixed relative to a concurrent ``write``."""
        with self._token_lock:
            self._token_flush_handle = None
            self._token_flush_armed = False
            batch, self._pending_tokens = self._pending_tokens, []
            if batch and not self._closed:
                self._loop.create_task(self._safe_send_many(batch))

    @property
    def closed(self) -> bool:
        return self._closed

    async def write_async(self, obj: dict) -> bool:
        """Send from the owning loop; awaits until the frame is on the wire. Buffered tokens are flushed
        ahead of it in the SAME batch so nothing slips between."""
        if self._closed:
            return False
        with self._token_lock:
            batch, self._pending_tokens = self._pending_tokens, []
            batch.append(json.dumps(obj, ensure_ascii=False))
        await self._safe_send_many(batch)
        return not self._closed

    async def _safe_send_many(self, lines: list[str]) -> None:
        """Send one indivisible batch of pre-serialized frames in wire order."""
        async with self._send_lock:
            if self._closed:
                return
            for line in lines:
                if self._closed:
                    return
                payload = _sanitize_ws_text(line)
                try:
                    await self._ws.send_text(payload)
                except UnicodeEncodeError as exc:
                    _log.warning("ws send skipped invalid utf-8 frame peer=%s error=%s", self._peer, exc)
                    continue
                except Exception as exc:
                    self._closed = True
                    _log.warning("ws send failed peer=%s error_type=%s error=%s", self._peer, type(exc).__name__, exc)
                    return

    def close(self) -> None:
        self._closed = True
        if self._token_flush_handle is not None:
            self._token_flush_handle.cancel()
            self._token_flush_handle = None


def _ws_peer_label(ws: Any) -> str:
    """``host:port`` when available, else a stable placeholder."""
    client = getattr(ws, "client", None)
    if client is None:
        return "unknown"
    host, port = getattr(client, "host", None) or "unknown", getattr(client, "port", None)
    return f"{host}:{port}" if port is not None else host


def _disable_nagle(ws: Any) -> None:
    """Disable Nagle + enable TCP keepalive on the raw socket (best-effort). Without TCP_NODELAY the kernel
    coalesces small per-token frames, so a burst after the model's think-pause lands in one tick and no
    client-side smoothing can recover the cadence. Without keepalive a silently-dropped client (SSH tunnel
    reset, sleep) leaves the leg half-open forever: receive_text() blocks and the disconnect teardown never runs."""
    try:
        scope = getattr(ws, "scope", None) or {}
        transport = (scope.get("extensions") or {}).get("transport") or getattr(ws, "transport", None)
        sock = transport.get_extra_info("socket") if transport is not None else None
        if sock is not None:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            if hasattr(socket, "TCP_KEEPIDLE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
            elif hasattr(socket, "TCP_KEEPALIVE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, 30)
    except Exception as exc:  # pragma: no cover - best-effort tuning
        _log.debug("ws TCP_NODELAY skip: %s", exc)


class _SendFailed(Exception):
    """Raised by handle_ws._reply when a reply could not be written: ends the read loop."""


async def handle_ws(ws: Any, *, auth_identity: dict | None = None, subprotocol: str | None = None) -> None:
    """Run one WebSocket session. Wire-compatible with ``tui_gateway.entry``. *auth_identity* is the server-minted
    ``{user_id, provider}`` recorded at WS-upgrade auth, stored as ``WSTransport.auth_identity`` (the only identity
    authority for browser-controller registration); callers that omit it (harnesses, embedded TUI child) get None."""
    peer, transport = _ws_peer_label(ws), None
    messages = parse_errors = dispatch_crashes = send_failures = 0
    disconnect_reason = "not_connected"

    async def _reply(frame: dict, reason: str, msg: str, *args: Any) -> None:
        """write_async; on failure record *reason*, log *msg* and end the read loop."""
        nonlocal disconnect_reason, send_failures
        if not await transport.write_async(frame):
            disconnect_reason = reason
            send_failures += 1
            _log.warning(msg, *args)
            raise _SendFailed

    def _error(code: int, message: str, req_id: Any) -> dict:
        return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": req_id}

    try:
        await (ws.accept(subprotocol=subprotocol) if subprotocol else ws.accept())
        disconnect_reason = "connected"
        _note_dashboard_client_activity(force=True)
        _disable_nagle(ws)
        _log.info("ws accepted peer=%s", peer)
        transport = WSTransport(ws, asyncio.get_running_loop(), peer=peer, auth_identity=auth_identity)
        skin_payload = await asyncio.to_thread(server.resolve_skin)
        ready_ok = await transport.write_async({
            "jsonrpc": "2.0", "method": "event",
            "params": {"type": "gateway.ready", "payload": {
                "skin": skin_payload, "change_events": True, "heartbeat": True, "replay_epoch": replay_epoch(),
            }},
        })
        if ready_ok:
            server._ensure_skin_watcher()
            server.register_live_transport(transport)
        for start, what in (
            (server._start_backend_heartbeat_refresher, "backend heartbeat refresher start"),
            (server._schedule_startup_orphan_sweep, "startup orphan sweep scheduling"),
        ):
            try:
                start()
            except Exception:
                _log.warning("%s failed", what, exc_info=True)
        if not ready_ok:
            disconnect_reason = "ready_send_failed"
            send_failures += 1
            _log.error("ws ready frame send failed peer=%s", peer)
            return

        while True:
            try:
                raw = await ws.receive_text()
                _note_dashboard_client_activity()
            except _WebSocketDisconnect as exc:
                disconnect_reason = f"client_disconnect(code={getattr(exc, 'code', None)},reason={getattr(exc, 'reason', None)})"
                break
            except Exception:
                disconnect_reason = "receive_failed"
                _log.exception("ws receive failed peer=%s", peer)
                break
            line = raw.strip()
            if not line:
                continue
            messages += 1
            try:
                req = json.loads(line)
            except json.JSONDecodeError as exc:
                parse_errors += 1
                _log.warning("ws parse error peer=%s index=%d error=%s payload=%r", peer, messages, exc, line[:_WS_LOG_PAYLOAD_PREVIEW])
                await _reply(_error(-32700, "parse error", None), "send_failed_after_parse_error",
                             "ws parse-error reply send failed peer=%s", peer)
                continue
            req_id = req.get("id") if isinstance(req, dict) else None
            req_method = req.get("method") if isinstance(req, dict) else None
            if req_method == "gateway.ping":
                await _reply({"jsonrpc": "2.0", "result": {"ok": True}, "id": req_id}, "send_failed_after_heartbeat",
                             "ws heartbeat reply send failed peer=%s id=%s", peer, req_id)
                continue
            try:
                resp = await asyncio.to_thread(server.dispatch, req, transport)
            except Exception:
                dispatch_crashes += 1
                _log.exception("ws dispatch crash peer=%s id=%s method=%s", peer, req_id, req_method)
                await _reply(_error(-32603, "internal error", req_id), "send_failed_after_dispatch_crash",
                             "ws dispatch-crash reply send failed peer=%s id=%s method=%s", peer, req_id, req_method)
                continue
            if resp is not None:
                await _reply(resp, "send_failed_after_response",
                             "ws response send failed peer=%s id=%s method=%s", peer, req_id, req_method)
    except _SendFailed:
        pass
    finally:
        reaped_sessions = detached_sessions = 0
        if transport is not None:
            server.unregister_live_transport(transport)
            try:
                from gateway.browser_control_broker import get_browser_control_broker
                await asyncio.to_thread(get_browser_control_broker().disconnect_owner, transport)
            except Exception:
                _log.exception("ws browser-controller disconnect failed peer=%s", peer)
            transport.close()
            try:
                await asyncio.to_thread(server._release_wake_for_transport, transport)
            except Exception:
                _log.exception("ws wake-word teardown failed peer=%s", peer)
            try:
                reaped_sessions, detached_sessions = await asyncio.to_thread(
                    server._close_sessions_for_transport, transport, end_reason="ws_disconnect"
                )
            except Exception:
                _log.exception("ws transport teardown failed peer=%s", peer)
        try:
            await ws.close()
        except Exception as exc:
            _log.debug("ws close failed peer=%s error=%s", peer, exc)
        _log.info(
            "ws closed peer=%s reason=%s messages=%d parse_errors=%d "
            "dispatch_crashes=%d send_failures=%d reaped_sessions=%d detached_sessions=%d",
            peer, disconnect_reason, messages, parse_errors, dispatch_crashes, send_failures, reaped_sessions, detached_sessions,
        )
