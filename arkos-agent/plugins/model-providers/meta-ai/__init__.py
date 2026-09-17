"""Meta Model API (Muse Spark) provider profile — https://api.meta.ai/v1.

Bundled from albertodepaola/arkos-meta-provider; rides entirely on
ProviderProfile hooks (zero core edits). The reasoning dial is emitted as a
top-level ``reasoning_effort`` kwarg — not ``extra_body.reasoning``, whose
emission is gated by a core host allowlist a third-party plugin must not edit.
"""

import os
from typing import Any

from agent.reasoning_effort import META_AI_EFFORTS, clamp_effort
from providers import register_provider
from providers.base import ProviderProfile


class MetaAIProfile(ProviderProfile):
    """Meta Model API — top-level reasoning_effort, self-contained."""

    _NON_CHAT_PREFIXES = ("muse-image-", "muse-voice-")

    def fetch_models(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 8.0,
    ) -> list[str] | None:
        """Fetch and filter the live catalog, excluding non-chat models."""
        live = super().fetch_models(api_key=api_key, base_url=base_url, timeout=timeout)
        if live is None:
            return None
        return [
            m for m in live
            if not any(m.startswith(p) for p in self._NON_CHAT_PREFIXES)
        ]

    def build_api_kwargs_extras(
        self, *, reasoning_config: dict | None = None, supports_reasoning: bool = False, **context: Any
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Ignores the core ``supports_reasoning`` gate (host-allowlist driven); Muse Spark always
        accepts ``reasoning_effort``. Muse 400s on ``none``: disabled/"none" -> ``minimal``
        (closest to off); unset/bespoke levels -> ``medium``."""
        rc = reasoning_config or {}
        effort = str(rc.get("effort") or "").strip().lower()
        if rc.get("enabled") is False or effort == "none":
            mapped = "minimal"
        else:
            clamped = clamp_effort(effort, META_AI_EFFORTS)
            mapped = clamped if clamped in META_AI_EFFORTS else "medium"
        return {}, {"reasoning_effort": mapped}


meta_ai = MetaAIProfile(
    name="meta-ai", aliases=("meta", "muse", "muse-spark", "model-api", "msl"), display_name="Meta Model API",
    description="Meta Muse Spark family (Meta Superintelligence Labs)",
    signup_url="https://developer.meta.com/ai/",
    env_vars=("MODEL_API_KEY", "META_API_KEY", "META_MODEL_API_KEY", "META_BASE_URL"),
    base_url=os.getenv("META_BASE_URL", "").strip() or "https://api.meta.ai/v1", auth_type="api_key",
    api_mode="codex_responses",
    supports_vision=True, supports_vision_tool_messages=False,
    default_aux_model="muse-spark-1.2-contributor",
    default_max_tokens=16384,
    fallback_models=("muse-spark-1.2",),
)

register_provider(meta_ai)
