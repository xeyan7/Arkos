"""Xiaomi MiMo provider profile."""

from providers import register_provider
from providers.base import ProviderProfile

xiaomi = ProviderProfile(
    name="xiaomi", aliases=("mimo", "xiaomi-mimo"), env_vars=("XIAOMI_API_KEY",),
    base_url="https://api.xiaomimimo.com/v1",
    supports_health_check=False,
    supports_vision=True,
    supports_vision_tool_messages=False,
)

register_provider(xiaomi)
