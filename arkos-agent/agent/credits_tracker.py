"""Engine build: Portal credits subsystem removed (portal deleted).

Kept as inert types + safe stubs so existing importers (`rate_limit_credits`,
`agent_init`, `conversation_loop`) keep working without portal headers.
All parse/seed/evaluate entry points return miss/empty/False.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Optional

from utils import is_truthy_value

logger = logging.getLogger(__name__)

_version_warning_emitted: bool = False
_VALID_DENOMINATOR_KINDS = frozenset({"subscription_cap", "none"})
_USD_RE = re.compile(r"^-?\d+\.\d{2}$")
_SENTINEL = object()


def _safe_int(value: Any) -> Any:
    """Exact int (money-safe) or ``_SENTINEL``. ``int()`` directly, NOT ``int(float())``
    (precision loss above 2**53 corrupts money); float-shaped strings fail."""
    try:
        return _SENTINEL if value is None else int(str(value))
    except (TypeError, ValueError):
        return _SENTINEL


@dataclass
class CreditsState:
    """Credits state parsed from x-portal-credits-* response headers."""

    version: int = 0
    remaining_micros: int = 0
    remaining_usd: str = ""
    subscription_micros: int = 0
    subscription_usd: str = ""
    subscription_limit_micros: Optional[int] = None
    subscription_limit_usd: Optional[str] = None
    rollover_micros: int = 0
    purchased_micros: int = 0
    purchased_usd: str = ""
    tool_pool_micros: int = 0
    tool_pool_gated_off: bool = False
    denominator_kind: str = "none"
    paid_access: bool = True
    disabled_reason: Optional[str] = None
    as_of_ms: int = 0
    captured_at: float = 0.0
    from_header: bool = False

    @property
    def has_data(self) -> bool:
        return self.captured_at > 0

    @property
    def age_seconds(self) -> float:
        return time.time() - self.captured_at if self.has_data else float("inf")

    @property
    def depleted(self) -> bool:
        """``paid_access == False`` ONLY — ``remaining_micros == 0`` is a false positive
        when the balance is zero but access is live (renewal pending)."""
        return not self.paid_access

    @property
    def used_fraction(self) -> Optional[float]:
        """Fraction of the subscription cap consumed in [0.0, 1.0]; None without a computable
        denominator. Guarded on the LIMIT FIELD (the real denominator), not ``denominator_kind``."""
        lim = self.subscription_limit_micros
        if not isinstance(lim, int) or lim <= 0:
            return None
        return max(0.0, min(1.0, (lim - self.subscription_micros) / lim))


CREDITS_NOTICE_KIND = "sticky"
CREDITS_RESTORED_TTL_MS = 8000
CREDITS_USAGE_BANDS: tuple[tuple[float, str, int], ...] = ((0.50, "info", 50), (0.75, "warn", 75), (0.90, "warn", 90))
CREDITS_USAGE_KEY = "credits.usage"
GRANT_UNSPENT_MIN_MICROS = 10_000


def new_credits_latch() -> dict:
    """Fresh notice latch for :func:`evaluate_credits_notices`; every producer builds it here so a new gate key lands everywhere."""
    return {"active": set(), "seen_below_90": False, "usage_band": None, "seen_grant_unspent": False}


@dataclass
class AgentNotice:
    """Driver-agnostic out-of-band notice (``AIAgent.notice_callback`` / ``notice_clear_callback``); each driver
    renders its own way. ``kind``/``ttl_ms`` stay expressive so a future config can switch v1's sticky notices to TTL."""

    text: str
    level: str = "info"
    kind: str = "sticky"
    ttl_ms: Optional[int] = None
    key: Optional[str] = None
    id: Optional[str] = None


def _sticky_notice(text: str, level: str, key: str) -> AgentNotice:
    return AgentNotice(text=text, level=level, kind=CREDITS_NOTICE_KIND, key=key, id=key)


def is_free_tier_model(model: str, base_url: str = "") -> bool:
    """Portal free-tier check — removed in engine build. Always False."""
    return False


def evaluate_credits_notices(state: CreditsState, latch: dict, *, model_is_free: bool = False) -> tuple[list[AgentNotice], list[str]]:
    """Reconcile credits notices against the latch (see :func:`new_credits_latch`); mutates ``latch`` IN
    PLACE. Pure — no I/O, no agent/run_agent imports. ``model_is_free`` suppresses ``credits.depleted`` (a
    depleted account on a free model keeps inferencing) WITHOUT emitting "restored" — that fires only on a
    genuine ``paid_access`` flip back to True. Returns ``(to_show, to_clear)``; caller emits to_clear FIRST.

    Engine build: Portal credits removed — always ([], [])."""
    return ([], [])


_HEADER_FIELDS: tuple[tuple, ...] = (
    ("remaining_micros", "micros"), ("subscription_micros", "signed"), ("rollover_micros", "micros"),
    ("purchased_micros", "micros"), ("as_of_ms", "micros"), ("tool_pool_micros", "micros", 0),
    ("remaining_usd", "usd"), ("subscription_usd", "usd"), ("purchased_usd", "usd"),
    ("paid_access", "bool", True),
    ("tool_pool_gated_off", "bool", False),
)


def _header_name(field: str) -> str:
    return "x-portal-" + ("" if field.startswith("tool_pool_") else "credits-") + field.replace("_", "-")


def _parse_field(kind: str, raw: Optional[str], default: Any = _SENTINEL) -> Any:
    """One header value → field value; ``default`` when absent, ``_SENTINEL`` on a contract violation."""
    if raw is None:
        return default
    if kind in ("micros", "signed"):
        val = _safe_int(raw)
        return _SENTINEL if val is _SENTINEL or (kind == "micros" and val < 0) else val
    if kind == "usd":
        return raw if _USD_RE.match(raw) else _SENTINEL
    flag = raw.strip().lower()
    return _SENTINEL if flag not in ("true", "false") else flag == "true"


def parse_credits_headers(headers: Mapping[str, str], provider: str = "") -> Optional[CreditsState]:
    """Portal credits headers — removed in engine build. Always None (miss)."""
    return None


def _fixture(remaining: str, subscription: str, limit: Optional[str] = None, purchased: Optional[str] = None,
             *, paid: bool = True, reason: Optional[str] = None) -> dict:
    """Fixture spec from *_usd strings; micros derived exactly (Decimal)."""
    d: dict = {}
    for field, usd in (("remaining", remaining), ("subscription", subscription), ("subscription_limit", limit), ("purchased", purchased)):
        if usd is not None:
            d[f"{field}_micros"], d[f"{field}_usd"] = int(Decimal(usd) * 1_000_000), usd
    if limit is not None:
        d["denominator_kind"] = "subscription_cap"
    d["paid_access"] = paid
    return d if reason is None else {**d, "disabled_reason": reason}


_DEV_FIXTURES: dict[str, dict] = {
    "healthy": _fixture("30.34", "18.00", "20.00", "12.34"),
    "sub_50pct": _fixture("10.00", "10.00", "20.00"),
    "sub_75pct": _fixture("5.00", "5.00", "20.00"),
    "sub_90pct": _fixture("2.00", "2.00", "20.00"),
    "grant_exhausted": _fixture("12.34", "0.00", "20.00", "12.34"),
    "depleted": _fixture("0.00", "0.00", None, "0.00", paid=False, reason="out_of_credits"),
    "debt": _fixture("0.00", "-5.00", "20.00", "0.00", paid=False, reason="out_of_credits"),
}


def dev_fixture_credits_state() -> Optional[CreditsState]:
    """Dev fixture — removed in engine build. Always None."""
    return None


def _credits_state_from_account(info) -> Optional[CreditsState]:
    """Portal account → CreditsState — removed in engine build. Always None."""
    return None


def _hydrate_seed_state(agent, state) -> None:
    """Install a seed CreditsState on the agent and fire the notice policy once. Primes the crossing gate:
    the cold-start snapshot IS the first observation, so a session opening in a band warns immediately."""
    agent._credits_state = state
    if getattr(agent, "_credits_session_start_micros", None) is None:
        agent._credits_session_start_micros = state.remaining_micros
    latch = getattr(agent, "_credits_latch", None)
    if isinstance(latch, dict) and state.used_fraction is not None:
        latch["seen_below_90"] = True
    if callable(emit := getattr(agent, "_emit_credits_notices", None)):
        emit()


def seed_credits_at_session_start(agent) -> bool:
    """Portal credits seed — removed in engine build (portal deleted). Always False."""
    return False
