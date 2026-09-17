"""Fallback delivery for GatewayStreamConsumer: continuation sends after edits
stop working, chunking, cursor cleanup, commentary and silence retraction."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Callable, Optional

from gateway.platforms.base import BasePlatformAdapter as _BasePlatformAdapter
from gateway.stream_consumer_fences import ensure_closed_code_fences

logger = logging.getLogger("gateway.stream_consumer")


class StreamFallbackMixin:
    """Non-streaming delivery paths used once progressive edits fail or the turn ends oddly."""

    async def _send_new_chunk(self, text: str, reply_to_id: Optional[str], *,
                              final: bool = False) -> Optional[str]:
        """Send a new chunk threaded to ``reply_to_id``; returns the new message_id."""
        text = self._clean_for_display(text)
        if not text.strip():
            return reply_to_id
        try:
            result = await self.adapter.send(
                chat_id=self.chat_id, content=text, reply_to=reply_to_id,
                metadata=self._metadata_for_send(final=final, expect_edits=not final))
            if not (result.success and result.message_id):
                self._edit_supported = False
                return reply_to_id
            self._message_id = str(result.message_id)
            self._track_preview_ids_from_result(result)
            self._already_sent = True
            self._last_sent_text = text
            self._notify_new_message()
            return str(result.message_id)
        except Exception as e:
            logger.error("Stream send chunk error: %s", e)
            return reply_to_id

    def _visible_prefix(self) -> str:
        """Return the visible text already shown in the streamed message."""
        prefix = self._last_sent_text or ""
        if self.cfg.cursor and prefix.endswith(self.cfg.cursor):
            prefix = prefix[:-len(self.cfg.cursor)]
        return self._clean_for_display(prefix)

    def _continuation_text(self, final_text: str) -> str:
        """Return only the part of final_text the user has not already seen."""
        prefix = self._fallback_prefix or self._visible_prefix()
        if prefix and final_text.startswith(prefix):
            return final_text[len(prefix):].lstrip()
        return final_text

    @staticmethod
    def _split_text_chunks(text: str, limit: int, len_fn: "Callable[[str], int]" = len,
                           ) -> list[str]:
        """Split text for fallback sends: newline-preferred, fence-balanced across chunks."""
        from gateway.platforms.helpers import split_text_fence_aware
        return split_text_fence_aware(text, limit, len_fn, prefer_paragraphs=False,
                                      balance_fences=True)

    def _truncate_for_stream(self, text: str, limit: int, len_fn: "Callable[[str], int]",
                             ) -> list[str]:
        """Split via the adapter's canonical truncate_message (platform-specific rules);
        non-base test doubles / legacy adapters keep the two-argument call shape."""
        truncate = getattr(self.adapter, "truncate_message", None)
        if not callable(truncate):
            return self._split_text_chunks(text, limit, len_fn)
        if isinstance(self.adapter, _BasePlatformAdapter):
            chunks = truncate(text, limit, len_fn=len_fn)
        else:
            chunks = truncate(text, limit)
        if not isinstance(chunks, (list, tuple)) or not all(isinstance(c, str) for c in chunks):
            return self._split_text_chunks(text, limit, len_fn)
        return list(chunks)

    async def _send_fallback_final(self, text: str) -> None:
        """Send the final continuation after streaming edits stop working (one flood retry
        per chunk)."""
        if getattr(self, "_egress_declined", False):
            logger.warning(
                "suppressing the fallback continuation: the connector already "
                "declined this destination for this run"
            )
            return
        final_text = ensure_closed_code_fences(self._clean_for_display(text))
        continuation = self._continuation_text(final_text)
        self._fallback_final_send = False
        if not continuation.strip():
            continuation = await self._fallback_when_nothing_unseen(final_text)
            if continuation is None:
                return

        _len_fn, raw_limit = self._fallback_len_budget()
        chunks = self._split_text_chunks(continuation, max(500, raw_limit - 100), len_fn=_len_fn)

        stale_message_id = self._message_id
        last_message_id: Optional[str] = None
        last_successful_chunk = ""
        sent_any_chunk = False
        for chunk in chunks:
            result = await self._send_with_flood_retry(
                content=chunk, retry_log="Flood control on fallback send, retrying in %.1fs")
            if not result or not result.success:
                self._already_sent = sent_any_chunk
                self._message_id = last_message_id
                self._last_sent_text = last_successful_chunk
                self._fallback_prefix = ""
                return
            sent_any_chunk = True
            last_successful_chunk = chunk
            last_message_id = result.message_id or last_message_id
            self._notify_new_message()

        if (stale_message_id and stale_message_id != last_message_id
                and not self._fallback_preserve_partial_messages and continuation == final_text):
            await self._delete_previews([stale_message_id], label="Fallback partial",
                                        skip_sentinel=False)

        self._message_id = last_message_id
        self._already_sent = True
        self._mark_final_delivered(record=final_text)
        self._last_sent_text = chunks[-1]
        self._fallback_prefix = ""
        self._fallback_preserve_partial_messages = False

    async def _fallback_when_nothing_unseen(self, final_text: str) -> Optional[str]:
        """Fallback entered but the visible prefix already covers ``final_text``: returns the
        continuation to send (the whole final when the prefix is from a *previous* segment)
        or None when the turn is settled here."""
        visible = self._visible_prefix()
        if (final_text.strip() and final_text == visible
                and getattr(self.adapter, "RESEND_FINAL_ON_EMPTY_STREAM_FALLBACK", False) is True):
            delivery = await self._send_empty_fallback_final(final_text)
            if delivery == "delivered":
                return None
            self._already_sent = True
            self._fallback_prefix = ""
            self._fallback_preserve_partial_messages = False
            self._final_content_delivered = delivery in {"ambiguous", "preview"}
            if delivery == "preview":
                self._record_turn_final_payload(final_text)
            elif delivery == "ambiguous":
                self._delivery_ambiguous = True
            else:
                self._final_response_sent = False
            return None
        if final_text.strip() and final_text != visible:
            return final_text
        if (self._message_id and self._last_sent_text and self.cfg.cursor
                and self._last_sent_text.endswith(self.cfg.cursor)):
            clean_text = self._last_sent_text[:-len(self.cfg.cursor)]
            with contextlib.suppress(Exception):
                result = await self._edit_message(message_id=self._message_id, content=clean_text)
                if result.success:
                    self._last_sent_text = clean_text
        self._already_sent = True
        self._mark_final_delivered(record=final_text)
        return None

    def _fallback_len_budget(self) -> "tuple[Callable[[str], int], int]":
        """(len_fn, raw_limit) for fallback chunking — per-chat cap/unit on base adapters."""
        raw_limit = getattr(self.adapter, "MAX_MESSAGE_LENGTH", 4096)
        _len_fn: "Callable[[str], int]" = len
        if isinstance(self.adapter, _BasePlatformAdapter):
            _len_fn = self.adapter.message_len_fn
            try:
                raw_limit = self.adapter.max_message_length_for_chat(self.chat_id)
                _len_fn = self.adapter.message_len_fn_for_chat(self.chat_id)
            except Exception as e:
                logger.debug("per-chat limit resolution failed: %s", e)
        return _len_fn, raw_limit

    async def _send_with_flood_retry(self, *, content: str, retry_log: str, reply_to=None):
        """adapter.send(final metadata) with ONE bounded flood retry; returns the last
        SendResult.  Exceptions propagate (callers decide whether a raise is "ambiguous")."""
        kwargs = dict(chat_id=self.chat_id, content=content,
                      metadata=self._metadata_for_send(final=True))
        if reply_to is not None:
            kwargs["reply_to"] = reply_to
        result = None
        for attempt in range(2):
            result = await self.adapter.send(**kwargs)
            if getattr(result, "success", False):
                break
            retry_delay = self._fallback_flood_retry_delay(result)
            if attempt or retry_delay is None:
                break
            logger.debug(retry_log, retry_delay)
            await asyncio.sleep(retry_delay)
        return result

    async def _send_empty_fallback_final(self, final_text: str) -> str:
        """Commit a completed answer after Telegram finalization fails: "delivered", "failed"
        (gateway may retry), "ambiguous" (a timeout may have landed) or "preview" (flood
        control; the complete preview is authoritative)."""
        stale_ids = self._stale_preview_ids(segment_only=True)
        try:
            result = await self._send_with_flood_retry(
                content=final_text, reply_to=self._initial_reply_to_id,
                retry_log="Flood control on empty fallback final send; retrying in %.1fs")
        except Exception as exc:
            logger.debug("Empty fallback final send failed: %s", exc)
            return "ambiguous" if self._send_failure_may_have_delivered(exc) else "failed"
        if not getattr(result, "success", False):
            if self._is_flood_error(result):
                return "preview"
            return "ambiguous" if self._send_failure_may_have_delivered(result) else "failed"

        new_message_id = getattr(result, "message_id", None)
        await self._delete_previews(stale_ids, skip=new_message_id, label="Empty fallback",
                                    retry_on_false=True)
        self._segment_preview_message_ids = set()
        self._message_id = new_message_id or "__no_edit__"
        self._already_sent = True
        self._mark_final_delivered()
        self._delivered_final_text = self._display_payload(final_text)
        self._last_sent_text = final_text
        self._fallback_prefix = ""
        self._fallback_preserve_partial_messages = False
        self._notify_new_message()
        return "delivered"

    @staticmethod
    def _send_failure_may_have_delivered(result_or_exc: Any) -> bool:
        """Return True for timeout failures where retrying may duplicate."""
        if getattr(result_or_exc, "retryable", None) is True:
            return False
        error = str(getattr(result_or_exc, "error", None) or result_or_exc).lower()
        name = result_or_exc.__class__.__name__.lower()
        return "timeout" in error or "timed out" in error or "timeout" in name

    def _fallback_flood_retry_delay(self, result: Any) -> float | None:
        """Return a bounded retry delay for a fallback send, if safe to retry."""
        if not self._is_flood_error(result):
            return None
        try:
            delay = float(getattr(result, "retry_after", None) or 3.0)
        except (TypeError, ValueError):
            delay = 3.0
        if delay > self._max_fallback_flood_retry_seconds:
            logger.debug("Flood control requests %.1fs; leaving final delivery to the gateway",
                         delay)
            return None
        return max(0.0, delay)

    def _is_flood_error(self, result) -> bool:
        """Check if a SendResult failure is due to flood control / rate limiting."""
        err_lower = (getattr(result, "error", "") or "").lower()
        return "flood" in err_lower or "retry after" in err_lower or "rate" in err_lower

    async def _flush_segment_tail_on_edit_failure(self) -> None:
        """Before a segment reset, send the unseen tail as a new message (and best-effort
        strip the stuck cursor from the partial)."""
        if not self._fallback_final_send:
            await self._try_strip_cursor()
        visible = self._fallback_prefix or self._visible_prefix()
        tail = self._accumulated
        if visible and tail.startswith(visible):
            tail = tail[len(visible):].lstrip()
        tail = self._clean_for_display(tail)
        if not tail.strip():
            return
        try:
            _md = dict(self.metadata) if self.metadata else {}
            _md["_interim_send"] = True
            result = await self.adapter.send(chat_id=self.chat_id, content=tail, metadata=_md)
            if result.success:
                self._already_sent = True
        except Exception as e:
            logger.error("Segment-break tail flush error: %s", e)

    async def _try_strip_cursor(self) -> None:
        """Best-effort edit removing a stuck cursor when entering fallback mode."""
        prefix = self._visible_prefix()
        if not self._has_real_preview() or not prefix.strip():
            return
        with contextlib.suppress(Exception):
            result = await self._edit_message(message_id=self._message_id, content=prefix)
            if getattr(result, "success", False):
                self._last_sent_text = prefix

    async def _send_commentary(self, text: str) -> bool:
        """Send a completed interim assistant commentary message."""
        text = self._clean_for_display(text)
        if not text.strip():
            return False
        try:
            _md = self._metadata_for_send(final=False) or {}
            _md["_interim_send"] = True
            _plat = getattr(getattr(self.adapter, "platform", None), "value", None)
            _platform_name = str(_plat or getattr(self.adapter, "name", "")).lower()
            _needs_reply_anchor = _platform_name in ("buzz", "slack", "mattermost", "feishu")
            result = await self.adapter.send(
                chat_id=self.chat_id, content=text,
                reply_to=self._initial_reply_to_id if _needs_reply_anchor else None, metadata=_md)
            if result.success:
                self._notify_new_message()
                self._delivered_commentary_texts.append(text)
            return result.success
        except Exception as e:
            logger.error("Commentary send error: %s", e)
            return False

    def _raw_message_limit(self) -> int:
        """Per-chat length budget (``message_len_fn`` units) before overflow splits; rich
        adapters may raise it via ``streaming_overflow_limit`` so a reply that fits one rich
        message isn't fragmented at the edit limit."""
        base = getattr(self.adapter, "MAX_MESSAGE_LENGTH", 4096)
        if isinstance(self.adapter, _BasePlatformAdapter):
            try:
                base = self.adapter.max_message_length_for_chat(self.chat_id)
            except Exception as e:
                logger.debug("max_message_length_for_chat failed: %s", e)
            try:
                cap = self.adapter.streaming_overflow_limit()
            except Exception as e:
                logger.debug("streaming_overflow_limit check failed: %s", e)
                cap = None
            if isinstance(cap, int) and cap > base:
                return cap
        return base

    async def _suppress_silence_marker(self) -> None:
        """Retract any streamed preview when the final reply is a bare silence marker.  Flags
        stay False: the gateway's whole-response filter turns the marker into "" so no
        fallback send happens either."""
        if self._native_stream_opened:
            await self._close_empty_native_bubble("Silence-marker native stream close failed: %s")

        await self._delete_previews(self._stale_preview_ids(), label="Silence-marker")
        self._preview_message_ids = set()
        self._message_id = None
        self._accumulated = self._stream_ledger = self._last_sent_text = ""
        self._already_sent = False
        self._clear_turn_final_flags()
        logger.info("Suppressed streamed intentional-silence marker (chat=%s)", self.chat_id)
