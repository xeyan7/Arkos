"""Ollama Cloud provider profile.

Top-level ``reasoning_effort`` on /v1/chat/completions accepts none|low|medium|
high|max (``max`` is undocumented but real — ~2.5x more thinking tokens on
DeepSeek V4); Arkos' ``xhigh`` maps to ``max``.
"""

from typing import Any

from agent.reasoning_effort import OLLAMA_CLOUD_EFFORTS, OLLAMA_CLOUD_OVERRIDES, clamp_effort
from providers import register_provider
from providers.base import ProviderProfile


class OllamaCloudProfile(ProviderProfile):
    """Ollama Cloud — maps xhigh→max via top-level reasoning_effort."""

    def build_api_kwargs_extras(
        self, *, reasoning_config: dict | None = None, supports_reasoning: bool = False, **ctx: Any
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Gated on ``supports_reasoning`` (resolved from the model's /api/show
        ``thinking`` capability) so non-thinking models get no meaningless field."""
        if not supports_reasoning or not reasoning_config or not isinstance(reasoning_config, dict):
            return {}, {}
        effort = (reasoning_config.get("effort") or "").strip().lower()
        if reasoning_config.get("enabled", True) is False or effort == "none":
            return {}, {"reasoning_effort": "none"}
        if not effort:
            return {}, {}
        clamped = clamp_effort(effort, OLLAMA_CLOUD_EFFORTS, OLLAMA_CLOUD_OVERRIDES)
        return {}, {"reasoning_effort": clamped} if clamped in OLLAMA_CLOUD_EFFORTS else {}


ollama_cloud = OllamaCloudProfile(
    name="ollama-cloud", aliases=("ollama_cloud",), default_aux_model="nemotron-3-nano:30b",
    env_vars=("OLLAMA_API_KEY",), base_url="https://ollama.com/v1",
)

register_provider(ollama_cloud)
