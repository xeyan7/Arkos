"""Rate-limit / credits header capture and low-credit notices for ``AIAgent``.

Parses provider response headers into ``_rate_limit_state`` / ``_credits_state`` and emits sticky notices.
Extracted from ``run_agent.py``; every method resolves through ``AIAgent``'s MRO unchanged.
"""
import logging
import os
from typing import Any

from utils import is_truthy_value

logger = logging.getLogger("run_agent")


def _response_headers(http_response: Any):
    """Headers of a response, or None when there is nothing to parse."""
    return getattr(http_response, "headers", None) if http_response is not None else None


def _pct(fraction) -> str:
    return ("%.0f%%" % (fraction * 100)) if fraction is not None else "n/a"


def _adopt_credits_state(agent, state) -> None:
    """Retain-last-known: overwrite state and latch session-start remaining on the first header ever seen."""
    agent._credits_state = state
    if agent._credits_session_start_micros is None:
        agent._credits_session_start_micros = state.remaining_micros


class RateLimitCreditsMixin:
    """Rate-limit + credits header capture and notices (see module docstring)."""

    def _capture_rate_limits(self, http_response: Any) -> None:
        """Parse x-ratelimit-* headers from an HTTP response and cache the state (never raises)."""
        headers = _response_headers(http_response)
        if not headers:
            return
        try:
            from agent.rate_limit_tracker import parse_rate_limit_headers
            state = parse_rate_limit_headers(headers, provider=self.provider)
            if state is not None:
                self._rate_limit_state = state
        except Exception:
            pass

    def get_rate_limit_state(self):
        """Return the last captured RateLimitState, or None."""
        return self._rate_limit_state

    def _capture_anthropic_response_headers(self, http_response: Any) -> None:
        """Capture rate-limit + credits state from Anthropic Messages response headers (the SDK's
        aggregated ``Message`` drops them). Fail-open."""
        self._capture_rate_limits(http_response)
        self._capture_credits(http_response)

    def _capture_credits(self, http_response: Any) -> None:
        """Portal credits capture — removed in engine build. No-op."""
        return

    def _emit_credits_notices(self) -> None:
        """Portal credits notices — removed in engine build. No-op."""
        return

    def _credits_notices_enabled(self) -> bool:
        """``display.credits_notices``, read once per agent and cached (UI noise, not correctness); fail-open True."""
        cached = getattr(self, "_credits_notices_enabled_cache", None)
        if cached is not None:
            return cached
        enabled = True
        try:
            from arkos_cli.config import load_config
            display = (load_config() or {}).get("display")
            if isinstance(display, dict) and "credits_notices" in display:
                enabled = bool(display["credits_notices"])
        except Exception:
            pass
        self._credits_notices_enabled_cache = enabled
        return enabled

    def get_credits_state(self):
        """Return the last captured CreditsState, or None."""
        return self._credits_state

    def get_credits_spent_micros(self):
        """Session-cumulative micros spent = first_seen_remaining - current_remaining. None if no data."""
        if self._credits_session_start_micros is None or self._credits_state is None:
            return None
        return self._credits_session_start_micros - self._credits_state.remaining_micros

    def _check_openrouter_cache_status(self, http_response: Any) -> None:
        """Log X-OpenRouter-Cache-Status; HITs count in ``_or_cache_hits``. Never raises."""
        headers = _response_headers(http_response)
        if not headers:
            return
        try:
            status = headers.get("x-openrouter-cache-status")
            if not status:
                return
            if status.upper() == "HIT":
                self._or_cache_hits += 1
                logger.info("OpenRouter response cache HIT (total: %d)", self._or_cache_hits)
            else:
                logger.debug("OpenRouter response cache %s", status.upper())
        except Exception:
            pass
