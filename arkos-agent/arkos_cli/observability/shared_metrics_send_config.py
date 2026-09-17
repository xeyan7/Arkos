"""Configuration for shared-metrics transmission."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = ""

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})

_warned_send_without_collection = False


@dataclass(frozen=True)
class SendConfig:
    """Resolved transmission settings."""

    enabled: bool
    send: bool
    endpoint: str


def _endpoint_is_safe(endpoint: str) -> bool:
    """Reject plaintext destinations unless they are loopback (so tests can use local HTTP)."""
    try:
        parsed = urlparse(endpoint)
    except ValueError:
        return False
    if parsed.scheme == "https":
        return True
    return parsed.scheme == "http" and (parsed.hostname or "") in _LOCAL_HOSTS


def resolve_send_config(config: dict | None) -> SendConfig:
    """Resolve transmission settings from config (endpoint: config > production default).

    ``send`` is False whenever transmission cannot legitimately happen, so callers never
    have to re-check the combination.
    """
    global _warned_send_without_collection

    raw = config if isinstance(config, dict) else {}
    telemetry = raw.get("telemetry")
    telemetry = telemetry if isinstance(telemetry, dict) else {}
    shared = telemetry.get("shared_metrics")
    shared = shared if isinstance(shared, dict) else {}

    enabled = shared.get("enabled") is True
    send_requested = shared.get("send") is True

    if send_requested and not enabled:
        if not _warned_send_without_collection:
            _warned_send_without_collection = True
            logger.error(
                "telemetry.shared_metrics.send is true but "
                "telemetry.shared_metrics.enabled is false — nothing is "
                "collected, so nothing can be sent. Enable collection or "
                "turn sending off."
            )
        return SendConfig(enabled=False, send=False, endpoint=DEFAULT_ENDPOINT)

    endpoint = shared.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.strip():
        endpoint = DEFAULT_ENDPOINT
    endpoint = endpoint.strip()

    if send_requested and not _endpoint_is_safe(endpoint):
        logger.error(
            "Refusing to send shared metrics to %r: telemetry must use https "
            "(or a localhost http endpoint for testing).",
            endpoint,
        )
        return SendConfig(enabled=enabled, send=False, endpoint=endpoint)

    return SendConfig(enabled=enabled, send=send_requested, endpoint=endpoint)


def reset_warning_latch_for_tests() -> None:
    """Clear the once-per-process error latch (test support only)."""
    global _warned_send_without_collection
    _warned_send_without_collection = False
