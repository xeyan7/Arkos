"""Request-local worker lifecycle, watchdog polling, and wait status."""

from agent import chat_completion_helpers as h


class _NonStreamRequest:
    """One non-streaming request on a worker thread, polled by the caller.

    State shared between the worker (``_call``) and the poll loop lives on the
    instance; ``_abort_request`` may run from the poll (stranger) thread.
    """

    def __init__(self, agent, api_kwargs: dict):
        self.agent = agent
        self.api_kwargs = api_kwargs
        self.result = {"response": None, "error": None}
        self.clients = h._RequestClientRegistry(agent)
        self.cancelled = False
        self.codex_token = object() if agent.api_mode == "codex_responses" else None
        self.codex_retired = False
        self.wd = h._resolve_nonstream_watchdogs(agent, api_kwargs)
        self.codex_watchdog_state = (
            h.SimpleNamespace(
                token=self.codex_token,
                lock=h.threading.Lock(),
                last_event_ts=None,
                last_progress_ts=None,
                retry_started_ts=None,
                phase_aware=self.wd.idle_requires_progress,
            )
            if self.codex_token is not None
            else None
        )
        self.call_start = h.time.time()
        self.wait_notice_started_ts = None
        self.thread = None

    def _install_codex_request_token(self) -> None:
        if self.codex_token is not None and not self.codex_retired:
            self.agent._active_codex_stream_request_token = self.codex_token

    def _retire_codex_request_token(self) -> None:
        if self.codex_token is None:
            return
        self.codex_retired = True
        if getattr(self.agent, "_active_codex_stream_request_token", None) is self.codex_token:
            self.agent._active_codex_stream_request_token = None

    def _make_client(self, reason: str, kind: str = "openai"):
        if kind == "anthropic_messages":
            client = self.agent._create_request_anthropic_client(reason=reason)
        else:
            client = self.agent._create_request_openai_client(reason=reason, api_kwargs=self.api_kwargs)
        return self.clients.set_client(client, kind=kind)

    def _call(self):
        watchdog_state_var = watchdog_context_token = None
        try:
            self._install_codex_request_token()
            if self.codex_watchdog_state is not None:
                from agent.codex_runtime import _codex_watchdog_state_var

                watchdog_state_var = _codex_watchdog_state_var
                watchdog_context_token = watchdog_state_var.set(self.codex_watchdog_state)
            self.result["response"] = h._dispatch_nonstreaming_api_request(
                self.agent, self.api_kwargs, make_client=self._make_client)
        except Exception as e:
            if self.codex_retired:
                h.logger.info("Codex worker caught %s after request retirement — "
                    "discarding the stale partial instead of surfacing it as a completed response. %s",
                    type(e).__name__, self.agent._client_log_context())
                return
            if self.cancelled:
                h.logger.debug("Non-streaming worker caught %s after request "
                    "cancellation — exiting without surfacing a network error.", type(e).__name__)
                return
            self.result["error"] = e
        finally:
            if watchdog_state_var is not None:
                watchdog_state_var.reset(watchdog_context_token)
            self._retire_codex_request_token()
            self.clients.close_once(
                "request_complete" if self.result["response"] is not None else "request_error_cleanup")

    def _abort_request(self, reason: str) -> None:
        """Watchdog/interrupt kill: abort the request client (kind-aware)
        and retire the codex token; the worker sees its own forced close via
        the cancel flags."""
        with h.contextlib.suppress(Exception):
            self.clients.close_once(reason)
        self._retire_codex_request_token()

    def _await_worker_after_kill(self, timeout_message: str) -> None:
        self.thread.join(timeout=2.0)
        if self.result["error"] is None and self.result["response"] is None:
            self.result["error"] = TimeoutError(timeout_message)

    def _model(self) -> str:
        return self.api_kwargs.get("model", "unknown")

    def _codex_watchdog_snapshot(self):
        state = self.codex_watchdog_state
        if state is None:
            return (None, None, None)
        with state.lock:
            return state.last_event_ts, state.last_progress_ts, state.retry_started_ts

    def _emit_wait_notice(self, elapsed: float, *, heartbeat: bool = True) -> None:
        wd = self.wd
        try:
            last_event_ts, last_progress_ts, retry_started_ts = self._codex_watchdog_snapshot()
            activity_ts = retry_started_ts if retry_started_ts is not None else last_event_ts
            if (self.wait_notice_started_ts is not None and activity_ts is not None
                    and activity_ts > self.wait_notice_started_ts):
                self.agent._emit_wait_notice("")
                self.wait_notice_started_ts = None
            if not heartbeat:
                return
            silence = self.call_start + elapsed - (
                activity_ts if activity_ts is not None else self.call_start)
            if silence < 60.0:
                self.agent._touch_activity(
                    "waiting for first stream event after reconnect"
                    if retry_started_ts is not None else "waiting for provider response")
                return
            status = "no response yet"
            if retry_started_ts is not None:
                status = "no response after reconnect"
            elif last_event_ts is not None:
                status = "no stream events"
            recovery = h._codex_wait_notice_recovery(stale_timeout=wd.stale_timeout,
                ttfb_enabled=wd.ttfb_enabled, ttfb_timeout=wd.ttfb_timeout,
                last_event_ts=last_event_ts, last_progress_ts=last_progress_ts,
                retry_started_ts=retry_started_ts,
                call_start=self.call_start, idle_enabled=wd.idle_enabled, idle_timeout=wd.idle_timeout,
                idle_requires_progress=wd.idle_requires_progress,
                elapsed=elapsed)
            if recovery and activity_ts is not None:
                recovery += " total elapsed"
            self.agent._emit_wait_notice(
                f"⏳ waiting on {self.api_kwargs.get('model', 'the provider')} — "
                f"{int(silence)}s with {status} (provider may be slow or overloaded{recovery})")
            self.wait_notice_started_ts = self.call_start + elapsed
        except Exception:
            h.logger.debug("wait-notice construction failed", exc_info=True)

    def _ttfb_kill(self, elapsed: float) -> None:
        """No parsed Codex event past the first-event cutoff — kill so the retry loop
        reconnects instead of waiting out the stale timeout."""
        agent, wd = self.agent, self.wd
        silent_hint = h._codex_silent_hang_hint(agent, self.api_kwargs)
        h.logger.warning("Codex stream produced no parsed stream event within TTFB cutoff "
            "(%.0fs > %.0fs, model=%s). Backend accepted the connection "
            "but sent no stream events. Killing connection so the retry loop can reconnect.", elapsed,
            wd.ttfb_timeout, self._model())
        agent._buffer_status(
            f"⚠️ No first stream event from provider in {int(elapsed)}s (codex stream, model: {self._model()}). "
            f"Reconnecting." + (f" {silent_hint}" if silent_hint else ""))
        self._abort_request("codex_ttfb_kill")
        agent._emit_wait_notice(f"⚠ no response from provider in {int(elapsed)}s — reconnecting...")
        agent._touch_activity(f"codex stream killed after {int(elapsed)}s with no first stream event")
        self._await_worker_after_kill(
            f"Codex stream produced no parsed stream event within {int(elapsed)}s "
            f"(TTFB threshold: {int(wd.ttfb_timeout)}s)"
            + (f". {silent_hint}" if silent_hint else ""))

    def _idle_kill(self, event_stale_elapsed: float) -> None:
        """SSE events stopped after the phase-specific idle arm point.

        Only the implicit official OpenAI Codex policy arms on substantive model
        progress; compatible providers and explicit operator timeouts arm on first
        parsed event. Once armed, any parsed SSE event refreshes transport activity.
        """
        agent, wd = self.agent, self.wd
        arm_point = "model progress began" if wd.idle_requires_progress else "the first parsed event"
        h.logger.warning("Codex stream produced no SSE events for %.0fs after %s "
            "(threshold %.0fs, model=%s, context=~%s tokens). Killing "
            "connection so the retry loop can reconnect.", event_stale_elapsed, arm_point, wd.idle_timeout,
            self._model(), f"{wd.est_tokens:,}")
        agent._buffer_status(
            f"⚠️ Codex stream sent no events for {int(event_stale_elapsed)}s after {arm_point} "
            f"(model: {self._model()}). Reconnecting.")
        self._abort_request("codex_stream_idle_kill")
        agent._touch_activity(f"codex stream killed after {int(event_stale_elapsed)}s with no SSE events")
        self._await_worker_after_kill(
            f"Codex stream produced no SSE events for {int(event_stale_elapsed)}s "
            f"after {arm_point} (threshold: {int(wd.idle_timeout)}s)")

    def _stale_kill(self, elapsed: float) -> None:
        """No response within the stale timeout: kill and count toward the
        circuit breaker (see ``_stale_streak``)."""
        agent, wd = self.agent, self.wd
        silent_hint = h._codex_silent_hang_hint(agent, self.api_kwargs)
        h._report_stale_nonstream_kill(agent, self.api_kwargs, elapsed, wd.stale_timeout, hint=silent_hint)
        self._abort_request("stale_call_kill")
        h._bump_stale_streak(agent)
        h._touch_stale_kill_activity(agent, elapsed)
        self._await_worker_after_kill(
            f"Non-streaming API call timed out after {int(elapsed)}s with no response (threshold: {int(wd.stale_timeout)}s)"
            + (f". {silent_hint}" if silent_hint else ""))

    def _interrupt(self, elapsed: float) -> None:
        agent = self.agent
        last_event_ts, _, _ = self._codex_watchdog_snapshot()
        h._record_interrupted_provider_wait(agent, elapsed,
            response_started=self.wd.codex and last_event_ts is not None
        )
        self.cancelled = True
        h.logger.debug("Force-closing httpx client due to interrupt (not a network error).")
        self._abort_request("interrupt_abort")
        h._join_worker_for_relay_teardown(self.thread, label="Non-streaming")
        raise InterruptedError("Agent interrupted during API call")

    def run(self):
        agent, wd = self.agent, self.wd
        if wd.codex:
            with self.codex_watchdog_state.lock:
                self.codex_watchdog_state.last_event_ts = None
                self.codex_watchdog_state.last_progress_ts = None
                self.codex_watchdog_state.retry_started_ts = None
        agent._touch_activity("waiting for non-streaming API response")

        self.thread = t = h.threading.Thread(target=h._context_thread_target(self._call), daemon=True)
        t.start()
        poll_count = 0
        while t.is_alive():
            t.join(timeout=0.3)
            poll_count += 1
            now = h.time.time()
            elapsed = now - self.call_start
            self._emit_wait_notice(elapsed, heartbeat=poll_count % 100 == 0)
            last_event_ts, last_progress_ts, retry_started_ts = self._codex_watchdog_snapshot()
            retry_ttfb_elapsed = now - retry_started_ts if retry_started_ts is not None else None
            if wd.ttfb_enabled and retry_ttfb_elapsed is not None and retry_ttfb_elapsed > wd.ttfb_timeout:
                self._ttfb_kill(retry_ttfb_elapsed)
                break
            if (retry_started_ts is None and wd.ttfb_enabled
                    and elapsed > wd.ttfb_timeout and last_event_ts is None):
                self._ttfb_kill(elapsed)
                break
            idle_elapsed = now - last_event_ts if last_event_ts is not None else None
            if (retry_started_ts is None and wd.idle_enabled and idle_elapsed is not None
                    and (not wd.idle_requires_progress or last_progress_ts is not None)
                    and idle_elapsed > wd.idle_timeout):
                self._idle_kill(idle_elapsed)
                break
            if elapsed > wd.stale_timeout:
                self._stale_kill(elapsed)
                break
            if agent._interrupt_requested:
                self._interrupt(elapsed)
        if self.result["error"] is not None:
            raise self.result["error"]
        if self.result["response"] is not None:
            h._reset_stale_streak(agent)
        return self.result["response"]
