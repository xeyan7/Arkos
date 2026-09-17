"""Shared platform registry for Arkos."""

from collections import OrderedDict
from typing import NamedTuple


class PlatformInfo(NamedTuple):
    """Metadata for a single platform entry."""
    label: str
    default_toolset: str


PLATFORMS: OrderedDict[str, PlatformInfo] = OrderedDict([
    ("cli",            PlatformInfo(label="🖥️  CLI",            default_toolset="arkos-cli")),
    ("telegram",       PlatformInfo(label="📱 Telegram",        default_toolset="arkos-telegram")),
    ("discord",        PlatformInfo(label="💬 Discord",         default_toolset="arkos-discord")),
    ("slack",          PlatformInfo(label="💼 Slack",           default_toolset="arkos-slack")),
    ("whatsapp",       PlatformInfo(label="📱 WhatsApp",        default_toolset="arkos-whatsapp")),
    ("whatsapp_cloud", PlatformInfo(label="📱 WhatsApp Business (Cloud)", default_toolset="arkos-whatsapp")),
    ("signal",         PlatformInfo(label="📡 Signal",          default_toolset="arkos-signal")),
    ("bluebubbles",    PlatformInfo(label="💙 BlueBubbles",     default_toolset="arkos-bluebubbles")),
    ("email",          PlatformInfo(label="📧 Email",           default_toolset="arkos-email")),
    ("homeassistant",  PlatformInfo(label="🏠 Home Assistant",  default_toolset="arkos-homeassistant")),
    ("mattermost",     PlatformInfo(label="💬 Mattermost",      default_toolset="arkos-mattermost")),
    ("matrix",         PlatformInfo(label="💬 Matrix",          default_toolset="arkos-matrix")),
    ("dingtalk",       PlatformInfo(label="💬 DingTalk",        default_toolset="arkos-dingtalk")),
    ("feishu",         PlatformInfo(label="🪽 Feishu",          default_toolset="arkos-feishu")),
    ("wecom",          PlatformInfo(label="💬 WeCom",           default_toolset="arkos-wecom")),
    ("wecom_callback", PlatformInfo(label="💬 WeCom Callback",  default_toolset="arkos-wecom-callback")),
    ("weixin",         PlatformInfo(label="💬 Weixin",          default_toolset="arkos-weixin")),
    ("qqbot",          PlatformInfo(label="💬 QQBot",           default_toolset="arkos-qqbot")),
    ("yuanbao",        PlatformInfo(label="🤖 Yuanbao",         default_toolset="arkos-yuanbao")),
    ("webhook",        PlatformInfo(label="🔗 Webhook",         default_toolset="arkos-webhook")),
    ("api_server",     PlatformInfo(label="🌐 API Server",      default_toolset="arkos-api-server")),
    ("cron",           PlatformInfo(label="⏰ Cron",            default_toolset="arkos-cron")),
])


def _plugin_label(entry) -> str:
    return f"{entry.emoji}  {entry.label}" if entry.emoji else entry.label


def platform_label(key: str, default: str = "") -> str:
    """Return the display label for a platform key (builtin, then plugin registry), or *default*."""
    info = PLATFORMS.get(key)
    if info is not None:
        return info.label
    try:
        from gateway.platform_registry import platform_registry
        entry = platform_registry.get(key)
        if entry:
            return _plugin_label(entry)
    except Exception:
        pass
    return default


def get_all_platforms() -> "OrderedDict[str, PlatformInfo]":
    """PLATFORMS plus plugin-registered platforms (appended after builtins) — use for menus."""
    merged = OrderedDict(PLATFORMS)
    try:
        from gateway.platform_registry import platform_registry
        for entry in platform_registry.plugin_entries():
            if entry.name not in merged:
                merged[entry.name] = PlatformInfo(_plugin_label(entry), f"arkos-{entry.name}")
    except Exception:
        pass
    return merged
