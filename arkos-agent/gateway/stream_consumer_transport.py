"""Transport layer of GatewayStreamConsumer: native frames, drafts, edit/send.

Mixin methods use only ``self`` state; see gateway/stream_consumer.py for the
state model and the drain loop that calls into these."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import Any, Optional

from gateway.platforms.base import BasePlatformAdapter as _BasePlatformAdapter
from gateway.stream_consumer_fences import ensure_closed_code_fences

logger = logging.getLogger("gateway.stream_consumer")


class StreamTransportMixin:
    """Send/edit/frame primitives and the transport-ordered ``_send_or_edit``."""

    _MIN_NEW_MSG_CHARS = 4

    async def _edit_message(self, *, message_id: str, content: str, finalize: bool = False):
        """Edit via the adapter, passing routing metadata when supported."""
        kwargs = dict(chat_id=self.chat_id, message_id=message_id, content=content,
                      finalize=finalize)
        if self.metadata:
            try:
                params = inspect.signature(self.adapter.edit_message).parameters
                if "metadata" in params or any(
                    param.kind is inspect.Parameter.VAR_KEYWORD for param in params.values()):
                    kwargs["metadata"] = self.metadata
            except (TypeError, ValueError):
                pass
        return await self.adapter.edit_message(**kwargs)

    async def _try_seed_frame(self, fail_log: str, *, exc_info: bool = False) -> bool:
        """Open a native stream with an empty seed frame (typing indicator before any token) as a
        bool; a raise logs ``fail_log`` at DEBUG (error formatted in, or the traceback when
        ``exc_info``) and reads as False."""
        seed = self.adapter.send_stream_frame(
            "", chat_id=self.chat_id, reply_to=self._initial_reply_to_id, turn_id=self._turn_id)
        return await self._try_frame(seed, fail_log, exc_info=exc_info)

    @staticmethod
    async def _try_frame(coro, fail_log: str, *, exc_info: bool = False) -> bool:
        """Await a frame send as a bool; a raise logs ``fail_log`` at DEBUG and reads as False."""
        try:
            return bool(await coro)
        except Exception as e:
            if exc_info:
                logger.debug(fail_log, exc_info=True)
            else:
                logger.debug(fail_log, e)
            return False

    async def _send_frame(self, text: str, *, finalize: bool):
        """One native-stream frame; every frame carries the same chat/reply/turn routing."""
        return await self.adapter.send_stream_frame(
            text, finalize=finalize, chat_id=self.chat_id, reply_to=self._initial_reply_to_id,
            turn_id=self._turn_id)

    def _close_native_state(self) -> None:
        """Mark the native stream closed (next content re-seeds or falls back)."""
        self._native_stream_opened = False
        self._native_last_pushed_len = 0

    async def _close_empty_native_bubble(self, fail_log: str) -> None:
        """Best-effort empty finalize frame to close an open typing bubble, then mark closed."""
        await self._try_frame(self._send_frame("", finalize=True), fail_log)
        self._close_native_state()
        self._reopen_seeded_eagerly = False

    def _degrade_native_to_buffered_send(self) -> None:
        """Leave native mode; buffer_only so post-boundary output is ONE send() at got_done
        (mid-stream flushes would create multiple messages on non-editable platforms)."""
        self._use_native_streaming = False
        self._close_native_state()
        self.cfg.buffer_only = True

    def _draft_metadata(self) -> dict | None:
        """Draft-frame metadata: same reply_to_message_id as the final send, because the
        relay adapter keys draft/seal state on it (flat DMs have no thread metadata)."""
        md = dict(self.metadata) if self.metadata else {}
        if self._initial_reply_to_id:
            md.setdefault("reply_to_message_id", self._initial_reply_to_id)
        return md or None

    def _stale_preview_ids(self, *, segment_only: bool = False) -> set:
        """Preview ids a fresh final replaces; ``segment_only`` spares finalized preambles."""
        stale_ids = set(self._segment_preview_message_ids if segment_only
                        else self._preview_message_ids)
        if self._message_id and self._message_id != "__no_edit__":
            stale_ids.add(str(self._message_id) if segment_only else self._message_id)
        return stale_ids

    async def _delete_previews(self, stale_ids, *, skip=None, label: str,
                               retry_on_false: bool = False, skip_sentinel: bool = True) -> None:
        """Best-effort delete of stale previews; never the message just sent (``skip``)."""
        delete_fn = getattr(self.adapter, "delete_message", None)
        if delete_fn is None:
            return
        for stale_id in stale_ids:
            if not stale_id or stale_id == skip or (skip_sentinel and stale_id == "__no_edit__"):
                continue
            try:
                deleted = await delete_fn(self.chat_id, stale_id)
                if retry_on_false and deleted is False:
                    await asyncio.sleep(1.0)
                    await delete_fn(self.chat_id, stale_id)
            except Exception as e:
                logger.debug("%s preview cleanup failed (%s): %s", label, stale_id, e)

    def _resolve_draft_streaming(self) -> bool:
        """cfg.transport "draft"/"auto" → the adapter's supports_draft_streaming probe
        ("draft" logs the downgrade); "edit"/"off" → False."""
        transport = (self.cfg.transport or "edit").lower()
        if transport in ("edit", "off") or not isinstance(self.adapter, _BasePlatformAdapter):
            return False
        probe_kwargs = dict(chat_type=self.cfg.chat_type or None, metadata=self.metadata)
        try:
            try:
                supported = self.adapter.supports_draft_streaming(chat_id=self.chat_id,
                                                                  **probe_kwargs)
            except TypeError:
                supported = self.adapter.supports_draft_streaming(**probe_kwargs)
        except Exception:
            logger.debug("supports_draft_streaming probe raised", exc_info=True)
            supported = False
        if not supported and transport == "draft":
            logger.debug("Draft streaming requested but unsupported (chat=%s, type=%r) — "
                         "falling back to edit", self.chat_id, self.cfg.chat_type)
        return bool(supported)

    def _resolve_native_streaming(self) -> bool:
        """Native streaming (send_stream_frame for ALL frames): a BasePlatformAdapter with
        class-level SUPPORTS_NATIVE_STREAMING and a truthy supports_native_streaming probe."""
        if not (isinstance(self.adapter, _BasePlatformAdapter)
                and getattr(type(self.adapter), "SUPPORTS_NATIVE_STREAMING", False)):
            return False
        probe = getattr(self.adapter, "supports_native_streaming", None)
        if probe is None:
            return False
        try:
            return bool(probe(chat_type=self.cfg.chat_type or None, metadata=self.metadata))
        except Exception:
            logger.debug("supports_native_streaming probe raised", exc_info=True)
            return False

    async def _send_draft_frame(self, text: str) -> bool:
        """Emit one draft frame; any failure permanently disables drafts for this run.
        Drafts have no message_id and clear on the client when the final send lands."""
        if self._draft_id is None:
            self._use_draft_streaming = False
            return False
        try:
            result = await self.adapter.send_draft(
                chat_id=self.chat_id, draft_id=self._draft_id, content=text,
                metadata=self._draft_metadata())
        except Exception as e:
            logger.debug("send_draft raised, disabling draft transport for this run: %s", e)
        else:
            if getattr(result, "success", False):
                self._last_sent_text = text
                return True
            from gateway.relay.egress import declined_send

            if declined_send(result):
                logger.warning(
                    "send_draft DECLINED by the connector's egress guard; "
                    "suppressing every later send for this run (the destination "
                    "is not approved for this connection)"
                )
                self._egress_declined = True
            logger.debug("send_draft returned success=False, disabling draft transport: %s",
                         getattr(result, "error", "unknown"))
        self._draft_failures += 1
        self._use_draft_streaming = False
        return False

    async def _abandon_native_stream(self) -> None:
        """Seal an orphaned draft stream on turn death (stale exit / cancel): else the live
        indicator stays forever and armed interception state leaks into the next turn.
        Never sets delivery flags."""
        if not self._use_draft_streaming:
            return
        if getattr(type(self.adapter), "abandon_open_draft", None) is None:
            return
        try:
            await self.adapter.abandon_open_draft(
                self.chat_id, self._last_sent_text or self._clean_for_display(self._accumulated),
                metadata=self._draft_metadata())
        except Exception as e:
            logger.debug("abandon_open_draft failed (best-effort): %s", e)

    def _has_real_preview(self) -> bool:
        """A real (editable, deletable) preview message id is on screen."""
        return bool(self._message_id) and self._message_id != "__no_edit__"

    def _should_send_fresh_final(self) -> bool:
        """True when fresh-final is enabled and a real preview has been visible ≥ threshold.

        Ported from upstream.
        """
        threshold = getattr(self.cfg, "fresh_final_after_seconds", 0.0) or 0.0
        if threshold <= 0 or not self._has_real_preview() or self._message_created_ts is None:
            return False
        return time.monotonic() - self._message_created_ts >= threshold

    def _track_preview_id(self, message_id: Optional[str]) -> None:
        """Record a real preview message id for finalization cleanup."""
        if message_id and message_id != "__no_edit__":
            message_id = str(message_id)
            self._preview_message_ids.add(message_id)
            self._segment_preview_message_ids.add(message_id)

    def _track_preview_ids_from_result(self, result: Any) -> None:
        """Record the primary id plus any continuation ids from an oversized split."""
        raw = getattr(result, "raw_response", None) or {}
        raw_ids = raw.get("message_ids") if isinstance(raw, dict) else None
        for mid in (getattr(result, "message_id", None),
                    *(getattr(result, "continuation_message_ids", None) or ()), *(raw_ids or ())):
            self._track_preview_id(mid)

    def _adapter_prefers_fresh_final(self, text: str) -> bool:
        """Adapter's prefers_fresh_final_streaming hook (Telegram's richer send path);
        False without a real preview / hook, or on any error."""
        fn = getattr(self.adapter, "prefers_fresh_final_streaming", None)
        if fn is None or not self._has_real_preview():
            return False
        try:
            try:
                result = fn(text, metadata=self.metadata, chat_id=self.chat_id)
            except TypeError:
                try:
                    result = fn(text, metadata=self.metadata)
                except TypeError:
                    result = fn(text)
        except Exception as e:
            logger.debug("prefers_fresh_final_streaming check failed: %s", e)
            return False
        return result is True

    async def _try_fresh_final(self, text: str, *, is_turn_final: bool = True) -> bool:
        """Send ``text`` fresh and best-effort delete the preview(s); False on any failure so
        the caller falls back to edit.  ``is_turn_final=False`` leaves the delivery flag unset.

        ``is_turn_final`` is False when finalizing an interim segment at a tool boundary (a preamble) rather
        than the turn-final answer; the final-delivery flag is then left unset so the gateway still delivers
        the real answer from the next API call.
        Ported from upstream.
        """
        if self._turn_split_delivery:
            return False
        stale_ids = self._stale_preview_ids()
        try:
            result = await self.adapter.send(
                chat_id=self.chat_id, content=text, metadata=self._metadata_for_send(final=True))
        except Exception as e:
            logger.debug("Fresh-final send failed, falling back to edit: %s", e)
            return False
        if not getattr(result, "success", False):
            return False
        new_message_id = getattr(result, "message_id", None)
        await self._delete_previews(stale_ids, skip=new_message_id, label="Fresh-final")
        self._preview_message_ids = set()
        self._adopt_message_id(new_message_id)
        self._already_sent = True
        self._last_sent_text = text
        if is_turn_final:
            self._final_response_sent = True
            self._record_turn_final_payload(text)
        return True

    def _adopt_message_id(self, message_id) -> None:
        """Retarget edits at ``message_id``; None → "__no_edit__" sentinel so we never edit it."""
        if message_id:
            self._message_id = message_id
            self._message_created_ts = time.monotonic()
        else:
            self._message_id = "__no_edit__"
            self._message_created_ts = None

    async def _send_or_edit(
        self, text: str, *, finalize: bool = False, is_turn_final: bool = True) -> bool:
        """Send or edit the streaming message; True if delivered.  ``finalize`` marks the
        last edit.  Transport order: native frame → draft frame → edit existing → first
        send; a transport returns None to fall through to the next."""
        text = self._clean_for_display(text)
        pre_fence_text = text
        text = ensure_closed_code_fences(text)
        visible_stripped = (text.replace(self.cfg.cursor, "") if self.cfg.cursor else text).strip()
        if not visible_stripped:
            if (finalize and self._use_native_streaming and self._native_stream_opened
                    and await self._try_frame(self._send_frame("✅", finalize=True),
                                              "Finalize empty stream failed: %s")):
                self._mark_final_delivered()
            return True
        if (self._message_id is None and self.cfg.cursor and self.cfg.cursor in text
                and len(visible_stripped) < self._MIN_NEW_MSG_CHARS):
            return True

        if self._use_native_streaming:
            ok = await self._native_push(text, finalize=finalize, is_turn_final=is_turn_final)
            if ok is not None:
                return ok
        if self._use_draft_streaming and self._message_id is None:
            ok = await self._draft_push(text, pre_fence_text, finalize=finalize,
                                        is_turn_final=is_turn_final)
            if ok is not None:
                return ok
        self._last_edit_overflowed = False
        try:
            if self._message_id is None:
                return await self._first_send(text, finalize=finalize)
            if not self._edit_supported:
                return False
            return await self._edit_existing(text, finalize=finalize, is_turn_final=is_turn_final)
        except Exception as e:
            logger.error("Stream send/edit error: %s", e)
            return False

    async def _native_push(self, text: str, *, finalize: bool, is_turn_final: bool,
                           ) -> Optional[bool]:
        """Native streaming: every frame goes through send_stream_frame(); lazy re-seed after
        a boundary.  None when native was disabled (seed/frame failure) → caller falls through."""
        if not self._native_stream_opened and text:
            if not await self._try_seed_frame("Re-seed failed, disabling native streaming: %s"):
                self._use_native_streaming = False
                return None
            self._native_stream_opened = True
            self._awaiting_reopen_after_boundary = False
            logger.info("[latency] Re-opened native stream after boundary "
                        "(turn=%s, waited for first delta)", self._turn_id)

        finalize = finalize and is_turn_final
        if not finalize and text == self._last_sent_text:
            return True

        if finalize:
            self._mark_final_delivered(record=text)
        if await self._try_frame(self._send_frame(text, finalize=finalize),
                                 "send_stream_frame raised, disabling native streaming: %s"):
            self._already_sent = True
            self._last_sent_text = text
            self._native_last_pushed_len = len(text)
            if finalize:
                self._mark_final_delivered()
            return True

        if finalize:
            self._final_response_sent = False
            self._final_content_delivered = False
            self._delivered_final_text = None
        self._use_native_streaming = False
        if self._native_stream_opened:
            try:
                await self._send_frame(text, finalize=True)
                logger.debug("Native fallback: finalized stream (best-effort close)")
            except Exception as e:
                logger.debug("Native fallback: failed to finalize stream: %s", e)
        return None

    async def _draft_push(self, text: str, pre_fence_text: str, *, finalize: bool,
                          is_turn_final: bool) -> Optional[bool]:
        """Draft frame while no message_id exists; None = not applicable / drafts just failed.
        Skipped when finalizing (the real send clears the draft), EXCEPT stream-is-the-message
        adapters keep ONE stream per turn: a segment-break finalize must not become a real
        send (it would seal at every tool boundary)."""
        stream_is_msg = self._stream_is_message()
        if finalize and not (stream_is_msg and not is_turn_final):
            return None
        frame_text = pre_fence_text if stream_is_msg else text
        if self.cfg.cursor and frame_text.endswith(self.cfg.cursor):
            frame_text = frame_text[: -len(self.cfg.cursor)]
        if frame_text == self._last_sent_text:
            return True
        return True if await self._send_draft_frame(frame_text) else None

    async def _first_send(self, text: str, *, finalize: bool) -> bool:
        """First send, threaded to the user's message (correct topic/thread)."""
        if getattr(self, "_egress_declined", False):
            logger.warning(
                "suppressing the plain-send fallback: the connector already "
                "declined this destination for this run"
            )
            return False
        result = await self.adapter.send(
            chat_id=self.chat_id, content=text, reply_to=self._initial_reply_to_id,
            metadata=self._metadata_for_send(final=finalize, expect_edits=not finalize))
        if not result.success:
            self._edit_supported = False
            return False
        self._already_sent = True
        self._last_sent_text = text
        if result.message_id:
            self._adopt_message_id(result.message_id)
            self._track_preview_ids_from_result(result)
        else:
            self._enter_fallback_mode(self._visible_prefix())
            self._message_id = "__no_edit__"
        self._notify_new_message()
        return True

    async def _edit_existing(self, text: str, *, finalize: bool, is_turn_final: bool) -> bool:
        """Edit the live preview (or replace it via fresh-final when finalizing)."""
        if text == self._last_sent_text and not (finalize and self._adapter_requires_finalize):
            return True
        has_prefers_hook = (
            hasattr(type(self.adapter), "prefers_fresh_final_streaming")
            or "prefers_fresh_final_streaming" in getattr(self.adapter, "__dict__", {}))
        prefers_fresh = self._adapter_prefers_fresh_final(text)
        if finalize and (
            prefers_fresh or (not has_prefers_hook and self._should_send_fresh_final())
        ) and await self._try_fresh_final(text, is_turn_final=is_turn_final):
            return True
        result = await self._edit_message(message_id=self._message_id, content=text,
                                          finalize=finalize)
        if not result.success:
            return await self._on_edit_failure(result, text, finalize=finalize,
                                               is_turn_final=is_turn_final)
        self._already_sent = True
        self._track_preview_ids_from_result(result)
        if ((getattr(result, "continuation_message_ids", ()) or ())
                and result.message_id and result.message_id != self._message_id):
            self._last_edit_overflowed = True
            self._turn_split_delivery = True
            self._adopt_message_id(str(result.message_id))
            self._last_sent_text = ""
            self._notify_new_message()
        else:
            self._last_sent_text = text
        self._flood_strikes = 0
        return True

    def _enter_fallback_mode(self, prefix: str) -> None:
        """Edits are over for this stream: send only the missing tail at got_done."""
        self._fallback_prefix = prefix
        self._fallback_final_send = True
        self._edit_supported = False
        self._already_sent = True

    async def _on_edit_failure(self, result, text: str, *, finalize: bool, is_turn_final: bool,
                               ) -> bool:
        """Classify a failed edit: partial overflow, flood backoff, or fallback mode.  Always
        False; the caller's finalize path may still deliver the tail."""
        from gateway.relay.egress import declined_send

        if declined_send(result):
            logger.warning(
                "edit DECLINED by the connector's egress guard; suppressing "
                "every later send for this run (the destination is not "
                "approved for this connection)"
            )
            self._egress_declined = True
            self._edit_supported = False
            return False
        turn_final = finalize and is_turn_final
        if (turn_final and self.cfg.cursor and self._last_sent_text.endswith(self.cfg.cursor)
                and self._visible_prefix() == text):
            self._final_content_delivered = True
            self._record_turn_final_payload(text)
        raw_response = getattr(result, "raw_response", None)
        if isinstance(raw_response, dict) and raw_response.get("partial_overflow"):
            self._message_id = str(raw_response.get("last_message_id") or result.message_id
                                   or self._message_id)
            delivered_prefix = raw_response.get("delivered_prefix")
            if isinstance(delivered_prefix, str) and delivered_prefix:
                self._last_sent_text = delivered_prefix
                self._fallback_preserve_partial_messages = text.startswith(delivered_prefix)
                self._enter_fallback_mode(delivered_prefix)
            else:
                self._fallback_preserve_partial_messages = False
                self._enter_fallback_mode(self._visible_prefix())
            if getattr(result, "continuation_message_ids", ()):
                self._notify_new_message()
            return False

        immediate_final_fallback = False
        if self._is_flood_error(result):
            self._flood_strikes += 1
            self._current_edit_interval = min(self._current_edit_interval * 2, 10.0)
            logger.debug("Flood control on edit (strike %d/%d), backoff interval → %.1fs",
                         self._flood_strikes, self._MAX_FLOOD_STRIKES, self._current_edit_interval)
            immediate_final_fallback = (
                turn_final and getattr(self.adapter, "FALLBACK_ON_FINAL_EDIT_FLOOD", False) is True)
            if self._flood_strikes < self._MAX_FLOOD_STRIKES and not immediate_final_fallback:
                self._last_edit_time = time.monotonic()
                return False
            if immediate_final_fallback:
                logger.debug("Turn-final edit hit flood control; entering fallback immediately")

        logger.debug("Edit failed (strikes=%d), entering fallback mode", self._flood_strikes)
        self._enter_fallback_mode(self._visible_prefix())
        if not immediate_final_fallback:
            await self._try_strip_cursor()
        return False
