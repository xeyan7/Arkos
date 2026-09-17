"""Platform scope rules for configured toolsets."""

from typing import Set


_TOOLSET_PLATFORM_RESTRICTIONS = {"discord": {"discord"}, "discord_admin": {"discord"}}


def toolset_allowed_for_platform(ts_key: str, platform: str) -> bool:
    """Return whether ``ts_key`` is available on ``platform``."""
    allowed: Set[str] | None = _TOOLSET_PLATFORM_RESTRICTIONS.get(ts_key)
    return allowed is None or platform in allowed
