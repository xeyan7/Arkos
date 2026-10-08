"""Headless tool configuration, provider metadata, and toolset policy for engine clients."""


import logging


import os


from typing import Dict, List, Optional, Set


from arkos_cli.config import cfg_get, load_config, save_config, get_env_value


from arkos_cli.platforms import PLATFORMS as _PLATFORMS_REGISTRY


from arkos_cli.toolset_scope import (
    _TOOLSET_PLATFORM_RESTRICTIONS, toolset_allowed_for_platform as _toolset_allowed_for_platform)


logger = logging.getLogger(__name__)


_warned_invalid_platform_toolsets: Set[str] = set()


PLATFORMS = {k: {"label": info.label, "default_toolset": info.default_toolset} for k, info in _PLATFORMS_REGISTRY.items()}


CONFIGURABLE_TOOLSETS = [
    ("web",             "🔍 Web Search & Scraping",    "web_search, web_extract"),
    ("browser",         "🌐 Browser Automation",       "navigate, click, type, scroll"),
    ("terminal",        "💻 Terminal & Processes",      "terminal, process"),
    ("file",            "📁 File Operations",           "read, write, patch, search"),
    ("code_execution",  "⚡ Code Execution",            "execute_code"),
    ("vision",          "👁️  Vision / Image Analysis",  "vision_analyze"),
    ("video",           "🎬 Video Analysis",            "video_analyze (requires video-capable model)"),
    ("image_gen",       "🎨 Image Generation",          "image_generate"),
    ("video_gen",       "🎬 Video Generation",          "video_generate (text/image/reference)"),
    ("x_search",        "🐦 X (Twitter) Search",        "x_search (requires xAI OAuth or XAI_API_KEY)"),
    ("tts",             "🔊 Text-to-Speech",            "text_to_speech"),
    ("stt",             "🎙️ Speech-to-Text",           "voice transcription (gateway voice messages + voice mode)"),
    ("skills",          "📚 Skills",                    "list, view, manage"),
    ("todo",            "📋 Task Planning",             "todo_list"),
    ("memory",          "💾 Memory",                    "persistent memory across sessions"),
    ("context_engine",  "🧩 Context Engine",            "runtime tools from the active context engine"),
    ("session_search",  "🔎 Session Search",            "search past conversations"),
    ("clarify",         "❓ Clarifying Questions",      "clarify"),
    ("delegation",      "👥 Task Delegation",           "delegate_task"),
    ("cronjob",         "⏰ Cron Jobs",                 "create/list/update/pause/resume/run, with optional attached skills"),
    ("homeassistant",    "🏠 Home Assistant",           "smart home device control"),
    ("spotify",          "🎵 Spotify",                  "playback, search, playlists, library"),
    ("discord",         "💬 Discord (read/participate)", "fetch messages, search members, create thread"),
    ("discord_admin",   "🛡️  Discord Server Admin",    "list channels/roles, pin, assign roles"),
    ("yuanbao",          "🤖 Yuanbao",                  "group info, member queries, DM"),
    ("computer_use",     "🖱️  Computer Use (macOS/Windows/Linux)", "background desktop control via cua-driver"),
]


def gui_toolset_label(label: str) -> str:
    """Strip the leading ``<emoji>`` from a toolset title for GUI surfaces (plugins prefix ``🔌``).
    CLI/TUI keeps the raw label — only HTTP APIs call this."""
    text = (label or "").strip()
    parts = text.split(None, 1)
    if len(parts) == 2 and not any(ch.isascii() and ch.isalnum() for ch in parts[0]):
        return parts[1].strip()
    return text


_DEFAULT_OFF_TOOLSETS = {"homeassistant", "spotify", "discord", "discord_admin", "video", "video_gen", "x_search", "a2a"}


def _xai_credentials_present() -> bool:
    """Cheap offline check for xAI credentials (auth store + env only); the runtime ``check_fn`` still gates
    schema registration if creds expire. Also used by ``provider_readiness_status`` for ``xai_grok`` rows."""
    try:
        from arkos_cli.auth import _read_xai_oauth_tokens
        _read_xai_oauth_tokens()
        return True
    except Exception:
        pass
    try:
        from tools.xai_http import get_env_value as _xai_get_env_value
        if str(_xai_get_env_value("XAI_API_KEY") or "").strip():
            return True
    except Exception:
        pass
    try:
        from agent.secret_scope import get_secret
    except ImportError:  # pragma: no cover — secret_scope is in-repo
        get_secret = os.environ.get
    return bool(str(get_secret("XAI_API_KEY") or "").strip())


def _homeassistant_credentials_present() -> bool:
    """Return whether the active profile has a Home Assistant token."""
    try:
        from agent.secret_scope import get_secret
        return bool((get_secret("HASS_TOKEN", "") or "").strip())
    except Exception:
        return False


def _get_effective_configurable_toolsets():
    """CONFIGURABLE_TOOLSETS + plugin toolsets (appended after built-ins; a plugin key already built-in is skipped)."""
    result = list(CONFIGURABLE_TOOLSETS)
    seen = {ts_key for ts_key, _, _ in result}
    try:
        from arkos_cli.plugins import discover_plugins, get_plugin_toolsets
        discover_plugins()
        for entry in get_plugin_toolsets():
            if entry[0] not in seen:
                seen.add(entry[0])
                result.append(entry)
    except Exception:
        pass
    return result


def _get_plugin_toolset_keys() -> set:
    """Return the set of toolset keys provided by plugins."""
    try:
        from arkos_cli.plugins import get_plugin_toolset_keys_nowait
        return get_plugin_toolset_keys_nowait()
    except Exception:
        return set()


def _platform_default_toolset(platform: str) -> str:
    """Composite toolset a platform falls back to (plugin platforms derive ``arkos-<platform>``)."""
    return PLATFORMS[platform]["default_toolset"] if platform in PLATFORMS else f"arkos-{platform}"


def _cfg_section(config: dict, key: str) -> dict:
    """Return ``config[key]`` as a dict, replacing a missing or non-dict value with ``{}``."""
    section = config.setdefault(key, {})
    if not isinstance(section, dict):
        section = {}
        config[key] = section
    return section


def _key(key: str, prompt: str, url: str = "", **extra) -> dict:
    """One ``env_vars`` entry for a provider row (key order matters for the GUI JSON)."""
    return {"key": key, "prompt": prompt, **extra, **({"url": url} if url else {})}


def _row(name: str, badge: str = "", tag: str = "", env_vars: list = (), **markers) -> dict:
    """One TOOL_CATEGORIES provider row; ``markers`` are the ``*_provider`` / ``post_setup`` keys."""
    row = {"name": name}
    if badge:
        row["badge"] = badge
    if tag:
        row["tag"] = tag
    row["env_vars"] = list(env_vars)
    row.update(markers)
    return row


_OPENAI_VOICE_KEY = _key("VOICE_TOOLS_OPENAI_KEY", "OpenAI API key", "https://platform.openai.com/api-keys")


_ELEVENLABS_KEY = _key("ELEVENLABS_API_KEY", "ElevenLabs API key", "https://elevenlabs.io/app/settings/api-keys")


_DEEPINFRA_KEY = _key("DEEPINFRA_API_KEY", "DeepInfra API key", "https://deepinfra.com/dash/api_keys")


_LANGFUSE_PUBLIC = ("ARKOS_LANGFUSE_PUBLIC_KEY", "Langfuse public key (pk-lf-...)")


_LANGFUSE_SECRET = ("ARKOS_LANGFUSE_SECRET_KEY", "Langfuse secret key (sk-lf-...)")


TOOL_CATEGORIES = {
    "tts": {
        "name": "Text-to-Speech", "icon": "🔊",
        "providers": [
            _row("Microsoft Edge TTS", "★ recommended · free", "Good quality, no API key needed", tts_provider="edge"),

            _row("OpenAI TTS", "paid", "High quality voices", [_OPENAI_VOICE_KEY], tts_provider="openai"),
            _row("xAI TTS", tag="Grok voices — uses xAI Grok OAuth or XAI_API_KEY", tts_provider="xai", post_setup="xai_grok"),
            _row("ElevenLabs", "paid", "Most natural voices", [_ELEVENLABS_KEY], tts_provider="elevenlabs"),
            _row("Mistral (Voxtral TTS)", "paid", "Multilingual, native Opus",
                 [_key("MISTRAL_API_KEY", "Mistral API key", "https://console.mistral.ai/")], tts_provider="mistral"),
            _row("Google Gemini TTS", "preview", "30 prebuilt voices, controllable via prompts",
                 [_key("GEMINI_API_KEY", "Gemini API key", "https://aistudio.google.com/app/apikey")], tts_provider="gemini"),
            _row("KittenTTS", "local · free", "Lightweight local ONNX TTS (~25MB), no API key", tts_provider="kittentts",
                 post_setup="kittentts"),
            _row("Piper", "local · free", "Local neural TTS, 44 languages (voices ~20-90MB)", tts_provider="piper",
                 post_setup="piper"),
            _row("DeepInfra TTS", "paid", "Chatterbox, Qwen3-TTS, … — live catalog from api.deepinfra.com", [_DEEPINFRA_KEY],
                 tts_provider="deepinfra"),
        ],
    },
    "stt": {
        "name": "Speech-to-Text", "icon": "🎙️",
        "providers": [
            _row("Local Whisper", "★ recommended · free", "faster-whisper on-device, no API key", stt_provider="local",
                 post_setup="faster_whisper"),

            _row("OpenAI", "paid", "whisper-1, gpt-4o-transcribe, gpt-transcribe", [_OPENAI_VOICE_KEY], stt_provider="openai"),
            _row("Groq", "free tier", "Whisper large-v3 family — very fast",
                 [_key("GROQ_API_KEY", "Groq API key", "https://console.groq.com/keys")], stt_provider="groq"),
            _row("xAI", tag="grok-stt — uses xAI Grok OAuth or XAI_API_KEY", stt_provider="xai", post_setup="xai_grok"),
            _row("ElevenLabs Scribe", "paid", "scribe_v2 — diarization + audio-event tagging", [_ELEVENLABS_KEY],
                 stt_provider="elevenlabs"),
            _row("DeepInfra", "paid", "Live STT catalog from api.deepinfra.com", [_DEEPINFRA_KEY], stt_provider="deepinfra"),
        ],
    },
    "web": {
        "name": "Web Search & Extract", "setup_title": "Select Search Provider",
        "setup_note": "A free DuckDuckGo search skill is also included — skip this if you don't need a premium provider.",
        "icon": "🔍",
        "providers": [

            {"name": "Firecrawl Self-Hosted", "badge": "free · self-hosted", "tag": "Run your own Firecrawl instance (Docker)",
             "web_backend": "firecrawl",
             "env_vars": [_key("FIRECRAWL_API_URL", "Your Firecrawl instance URL (e.g., http://localhost:3002)")]},
        ],
    },
    "image_gen": {
        "name": "Image Generation", "icon": "🎨",
        "providers": [

        ],
    },
    "video_gen": {
        "name": "Video Generation", "icon": "🎬",
        "providers": [

        ],
    },
    "x_search": {
        "name": "X (Twitter) Search", "setup_title": "Select xAI Credential Source",
        "setup_note": (
            "Arkos routes X searches through xAI's built-in x_search Responses tool for read-only public X "
            "discovery. Use the xurl skill for authenticated X API reads and account actions. Both credential "
            "sources hit the same https://api.x.ai/v1/responses endpoint — pick whichever you already have. "
            "SuperGrok OAuth is preferred when both are set (uses your subscription quota instead of API spend)."
        ),
        "icon": "🐦",
        "providers": [
            _row("xAI Grok OAuth (SuperGrok / Premium+)", "subscription", "Browser login at accounts.x.ai — no API key required",
                 post_setup="xai_grok"),
            _row("xAI API key", "paid", "Direct xAI API billing via XAI_API_KEY",
                 [_key("XAI_API_KEY", "xAI API key", "https://console.x.ai/")]),
        ],
    },
    "browser": {
        "name": "Browser Automation", "icon": "🌐",
        "providers": [
            _row("Local Browser", "★ recommended · free", "Headless Chromium, no API key needed", browser_provider="local",
                 browser_engine="auto", post_setup="agent_browser"),
            _row("Lightpanda", "free · local · no Chromium", "Zig headless browser spawned by Arkos, text-only (no screenshots)",
                 browser_provider="local", browser_engine="lightpanda", post_setup="lightpanda"),

            _row("Camofox", "free · local", "Anti-detection browser (Firefox/Camoufox)",
                 [_key("CAMOFOX_URL", "Camofox server URL", "https://github.com/jo-inc/camofox-browser", default="http://localhost:9377")],
                 browser_provider="camofox", post_setup="camofox"),
            _row("Browser Use", "free · local · cloud", "New SOTA web harness (CLI 3.0)", browser_backend="browser-use",
                 post_setup="browser_use_cli"),
        ],
    },
    "homeassistant": {
        "name": "Smart Home", "icon": "🏠",
        "providers": [
            _row("Home Assistant", tag="REST API integration",
                 env_vars=[_key("HASS_TOKEN", "Home Assistant Long-Lived Access Token"),
                           _key("HASS_URL", "Home Assistant URL", default="http://homeassistant.local:8123")]),
        ],
    },
    "spotify": {
        "name": "Spotify", "icon": "🎵",
        "providers": [_row("Spotify Web API", tag="PKCE OAuth — opens the setup wizard", post_setup="spotify")],
    },
    "computer_use": {
        "name": "Computer Use (macOS/Windows/Linux)", "icon": "🖱️",
        "platform_gate": ["darwin", "win32", "linux"],
        "providers": [
            _row("cua-driver (background)", "★ recommended · free · local",
                 "Background computer-use via cua-driver — does NOT steal your cursor or focus. Works with any model.",
                 computer_use_backend="cua", post_setup="cua_driver"),
        ],
    },
    "langfuse": {
        "name": "Langfuse Observability", "icon": "📊",
        "providers": [
            _row("Langfuse Cloud", tag="Hosted Langfuse (cloud.langfuse.com)", post_setup="langfuse",
                 env_vars=[_key(*_LANGFUSE_PUBLIC, "https://cloud.langfuse.com"), _key(*_LANGFUSE_SECRET, "https://cloud.langfuse.com")]),
            _row("Langfuse Self-Hosted", tag="Self-hosted Langfuse instance", post_setup="langfuse",
                 env_vars=[_key(*_LANGFUSE_PUBLIC), _key(*_LANGFUSE_SECRET),
                           _key("ARKOS_LANGFUSE_BASE_URL", "Langfuse server URL (e.g. http://localhost:3000)", default="http://localhost:3000")]),
        ],
    },
}


TOOLSET_ENV_REQUIREMENTS = {"vision": [("OPENROUTER_API_KEY", "https://openrouter.ai/keys")]}


def _parse_enabled_flag(value, default: bool = True) -> bool:
    """Parse bool-like config values used by tool/platform settings."""
    if isinstance(value, (bool, int)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on", "false", "0", "no", "off"}:
            return lowered in {"true", "1", "yes", "on"}
    return default


def enabled_mcp_server_names(config: dict) -> Set[str]:
    """MCP servers globally enabled in config.yaml or by a plugin (shared by platform + cron resolvers). Enabled
    unless ``enabled`` is explicitly falsey; portable-plugin servers (in-memory) count — enabling the plugin is
    the opt-in."""
    mcp_servers = (config or {}).get("mcp_servers") or {}
    names = {
        str(name) for name, server_cfg in mcp_servers.items()
        if isinstance(server_cfg, dict) and _parse_enabled_flag(server_cfg.get("enabled", True), default=True)
    }
    try:
        from arkos_cli.plugins import get_portable_mcp_server_names_nowait
        portable = get_portable_mcp_server_names_nowait()
        names |= portable - set(mcp_servers)
    except Exception:
        logger.debug("Failed to include portable MCP servers", exc_info=True)
    return names


_RECENTLY_SHIPPED_TOOLSETS: frozenset = frozenset()


def _enable_recently_shipped_toolsets(enabled_toolsets: Set[str], config: dict, platform: str) -> None:
    """Turn on toolsets that shipped after this platform's saved list (mutates ``enabled_toolsets``). Both "no"s
    outlive this: unchecking records ``known_builtin_toolsets`` (declined), and ``agent.disabled_toolsets`` is
    subtracted last in :func:`_get_platform_tools`."""
    from toolsets import resolve_toolset

    offered = (config.get("known_builtin_toolsets") or {}).get(platform)
    declined = {str(ts) for ts in offered} if isinstance(offered, list) else set()
    default_ts = _platform_default_toolset(platform)
    composite_tools = None
    for ts_key in sorted(_RECENTLY_SHIPPED_TOOLSETS):
        if ts_key in enabled_toolsets or ts_key in declined or not _toolset_allowed_for_platform(ts_key, platform):
            continue
        ts_tools = set(resolve_toolset(ts_key, include_registry=False))
        if composite_tools is None:
            composite_tools = set(resolve_toolset(default_ts))
        if not ts_tools or not ts_tools.issubset(composite_tools):
            continue
        enabled_toolsets.add(ts_key)


def _configurable_subset_of(tool_names: Set[str], platform: str) -> Set[str]:
    """Configurable toolsets whose STATIC membership is within ``tool_names`` (``include_registry=False``: a
    runtime-registered tool the composite never listed must not drop the whole toolset)."""
    from toolsets import resolve_toolset

    return {
        ts_key for ts_key, _, _ in CONFIGURABLE_TOOLSETS if _toolset_allowed_for_platform(ts_key, platform)
        and (ts_tools := set(resolve_toolset(ts_key, include_registry=False))) and ts_tools <= tool_names}


def _default_off_toolsets(platform: str, explicitly_configured: bool) -> Set[str]:
    """Toolsets to strip from an implicit (composite-derived) enable set. A platform named after a default-off
    toolset (``homeassistant``) keeps it, except platform-restricted ones (``discord`` on discord stays OFF); a
    configured HASS_TOKEN is an explicit opt-in that must survive platforms resolving without a saved list.
    Platform-native default-off toolsets (``discord`` on discord) are off for unconfigured platforms as a
    security opt-in — an explicitly saved list IS that opt-in and lets them through."""
    default_off = set(_DEFAULT_OFF_TOOLSETS)
    if platform in default_off and platform not in _TOOLSET_PLATFORM_RESTRICTIONS:
        default_off.remove(platform)
    if "homeassistant" in default_off and _homeassistant_credentials_present():
        default_off.remove("homeassistant")
    if explicitly_configured:
        default_off -= {ts for ts in default_off if platform in (_TOOLSET_PLATFORM_RESTRICTIONS.get(ts) or ())}
    return default_off


def _configurable_keys() -> Set[str]:
    return {ts_key for ts_key, _, _ in CONFIGURABLE_TOOLSETS}


def _platform_default_keys() -> Set[str]:
    return {p["default_toolset"] for p in PLATFORMS.values()}


def _explicit_toolsets(
    toolset_names: List[str], explicit_known_keys: Set[str], config: dict, platform: str,
    explicitly_configured: bool) -> Set[str]:
    """Enabled set when the saved list names configurable/plugin keys directly (subset inference over
    ``arkos-cli`` would re-enable disabled toolsets). A mixed list (``[arkos-cli, spotify]``) still expands the
    composite; _DEFAULT_OFF_TOOLSETS applies to that implicit expansion only."""
    from toolsets import resolve_toolset, TOOLSETS

    enabled = {ts for ts in toolset_names if ts in explicit_known_keys and _toolset_allowed_for_platform(ts, platform)}
    composite_tools = {
        t for ts_name in toolset_names if ts_name not in explicit_known_keys and ts_name in TOOLSETS
        for t in resolve_toolset(ts_name)}
    if composite_tools:
        enabled |= _configurable_subset_of(composite_tools, platform) - _default_off_toolsets(platform, explicitly_configured)
    _enable_recently_shipped_toolsets(enabled, config, platform)
    return enabled


def _composite_toolsets(toolset_names: List[str], platform: str, explicitly_configured: bool) -> Set[str]:
    """Enabled set inferred from composite names by reverse-mapping tool names (only while no explicit list is
    saved). ``x_search`` is not in any composite, so inject it when xAI creds exist and exempt it from default-off."""
    from toolsets import resolve_toolset

    all_tool_names = {t for ts_name in toolset_names for t in resolve_toolset(ts_name)}
    enabled = _configurable_subset_of(all_tool_names, platform)
    default_off = _default_off_toolsets(platform, explicitly_configured)
    if _toolset_allowed_for_platform("x_search", platform) and _xai_credentials_present():
        enabled.add("x_search")
        default_off.discard("x_search")
    return enabled - default_off


def _enabled_plugin_toolsets(config: dict, platform: str, toolset_names: List[str], plugin_ts_keys: Set[str]) -> Set[str]:
    """Plugin toolsets: on by default unless default-off (bundled spotify) or "known" for this platform
    (``known_plugin_toolsets``, written on every save) and absent from the saved list."""
    known_for_platform = set((config.get("known_plugin_toolsets", {}) or {}).get(platform, []) or [])
    return {
        pts for pts in plugin_ts_keys
        if pts in toolset_names or (pts not in _DEFAULT_OFF_TOOLSETS and pts not in known_for_platform)
    }


def _context_engine_active(config: dict) -> bool:
    context_cfg = config.get("context") or {}
    name = str(context_cfg.get("engine") or "compressor").strip().lower() if isinstance(context_cfg, dict) else "compressor"
    return bool(name) and name != "compressor"


def _get_platform_tools(config: dict, platform: str, *, include_default_mcp_servers: bool = True) -> Set[str]:
    """Resolve which individual toolset names are enabled for a platform."""
    platform_toolsets = config.get("platform_toolsets") or {}
    toolset_names = platform_toolsets.get(platform)
    explicitly_configured = isinstance(toolset_names, list)
    if not explicitly_configured:
        toolset_names = [_platform_default_toolset(platform)]
    toolset_names = [str(ts) for ts in toolset_names]

    configurable_keys = _configurable_keys()
    plugin_ts_keys = _get_plugin_toolset_keys()
    platform_default_keys = _platform_default_keys()
    explicit_known_keys = configurable_keys | plugin_ts_keys

    if any(ts in explicit_known_keys for ts in toolset_names):
        enabled_toolsets = _explicit_toolsets(toolset_names, explicit_known_keys, config, platform, explicitly_configured)
    else:
        enabled_toolsets = _composite_toolsets(toolset_names, platform, explicitly_configured)

    _recover_platform_native_toolsets(enabled_toolsets, platform, skip=configurable_keys | plugin_ts_keys | platform_default_keys)
    if plugin_ts_keys:
        enabled_toolsets |= _enabled_plugin_toolsets(config, platform, toolset_names, plugin_ts_keys)

    if _context_engine_active(config) and not (explicitly_configured and not toolset_names):
        enabled_toolsets.add("context_engine")

    explicit_passthrough = {ts for ts in toolset_names if ts not in explicit_known_keys and ts not in platform_default_keys}
    enabled_toolsets |= _merge_mcp_servers(config, toolset_names, explicit_passthrough, include_default_mcp_servers)

    disabled_toolsets = (config.get("agent") or {}).get("disabled_toolsets")
    if disabled_toolsets:
        from agent.skill_utils import parse_config_string_list
        disabled_names = [name.strip() for name in parse_config_string_list(disabled_toolsets) if name.strip()]
        enabled_toolsets = _prune_toolsets_stripped_by_disabled(enabled_toolsets, disabled_names)

    if explicitly_configured and toolset_names:
        _warn_all_invalid_platform_toolsets(platform, platform_toolsets[platform])
    return enabled_toolsets


def _prune_toolsets_stripped_by_disabled(enabled_toolsets: Set[str], disabled_names: List[str]) -> Set[str]:
    """Drop disabled names AND every toolset whose tools the runtime would strip anyway.

    The agent subtracts ``agent.disabled_toolsets`` at TOOL granularity (``model_tools._select_tool_names``),
    so disabling a composite like ``debugging`` removes the terminal/web/file tools even though those names
    never appear in the list. A name-only subtraction here left inspection surfaces (``arkos tools
    --summary``, banner, ``/tools``) showing toolsets as enabled that no session could call.
    Passthrough entries (MCP server names) and toolsets with no static tools (``context_engine``) are kept.
    """
    from model_tools import _apply_toolset_selection
    from toolsets import resolve_toolset, validate_toolset

    remaining = enabled_toolsets - set(disabled_names)
    resolved = {name: set(resolve_toolset(name)) if validate_toolset(name) else set() for name in remaining}
    surviving: Set[str] = set().union(*resolved.values())
    _apply_toolset_selection(surviving, disabled_names, quiet_mode=True, disable=True)
    return {name for name, tools in resolved.items() if not tools or tools & surviving}


def _recover_platform_native_toolsets(enabled_toolsets: Set[str], platform: str, *, skip: Set[str]) -> None:
    """Add non-configurable platform toolsets (discord, feishu_*) in place: in the default composite but not in
    CONFIGURABLE_TOOLSETS, so never in a checklist or saved list. Runs for BOTH ``_get_platform_tools`` branches."""
    from toolsets import resolve_toolset, TOOLSETS

    platform_tool_universe = set(resolve_toolset(_platform_default_toolset(platform)))
    configurable_tool_universe = {t for ts_key, _, _ in CONFIGURABLE_TOOLSETS for t in resolve_toolset(ts_key)}
    claimed = {t for ts_key in enabled_toolsets for t in resolve_toolset(ts_key)}
    skip = skip | {k for k in TOOLSETS if k.startswith("arkos-")} | (set(_DEFAULT_OFF_TOOLSETS) - {platform})
    for ts_key, ts_def in TOOLSETS.items():
        if ts_key in skip or ts_def.get("includes") or ts_def.get("posture"):
            continue
        ts_tools = set(resolve_toolset(ts_key, include_registry=False))
        if not ts_tools or not ts_tools <= platform_tool_universe or ts_tools <= configurable_tool_universe:
            continue
        if not ts_tools <= claimed:
            enabled_toolsets.add(ts_key)
            claimed.update(ts_tools)


def _merge_mcp_servers(
    config: dict, toolset_names: List[str], explicit_passthrough: Set[str], include_default_mcp_servers: bool
) -> Set[str]:
    """Explicit passthrough entries plus this platform's MCP servers: listed names form an allowlist, else every
    globally enabled server (when ``include_default_mcp_servers``); the ``no_mcp`` sentinel disables all."""
    enabled_mcp_servers = enabled_mcp_server_names(config)
    result = explicit_passthrough - enabled_mcp_servers
    if "no_mcp" in toolset_names:
        return result - {"no_mcp"}
    explicit_mcp_servers = explicit_passthrough & enabled_mcp_servers
    if include_default_mcp_servers and not explicit_mcp_servers:
        return result | enabled_mcp_servers
    return result | explicit_mcp_servers


def _warn_all_invalid_platform_toolsets(platform: str, explicit: list) -> None:
    """Warn once when an explicit platform list has only invalid names (``arkos`` for ``arkos-cli`` → no
    native tools), at session tool resolution rather than only in update/doctor."""
    from toolsets import validate_toolset

    named = [str(t) for t in explicit if isinstance(t, str) and t]
    if named and not any(validate_toolset(t) for t in named) and platform not in _warned_invalid_platform_toolsets:
        _warned_invalid_platform_toolsets.add(platform)
        logger.warning(
            "platform '%s' has no valid toolsets configured (unknown "
            "name(s): %s) - tools will be unavailable. Run `arkos tools` "
            "to reconfigure..",
            platform, ", ".join(named))


def _save_platform_tools(config: dict, platform: str, enabled_toolset_keys: Set[str]):
    """Save the selected toolset keys for a platform to config."""
    config.setdefault("platform_toolsets", {})
    enabled_toolset_keys = {ts for ts in enabled_toolset_keys if _toolset_allowed_for_platform(ts, platform)}
    plugin_keys = _get_plugin_toolset_keys()
    drop = _configurable_keys() | plugin_keys | _platform_default_keys() | {"no_mcp"}
    existing_toolsets = cfg_get(config, "platform_toolsets", platform, default=[])
    preserved_entries = {str(e) for e in (existing_toolsets if isinstance(existing_toolsets, list) else [])
                         if str(e) not in drop}
    config["platform_toolsets"][platform] = sorted(enabled_toolset_keys | preserved_entries)
    if plugin_keys:
        _cfg_section(config, "known_plugin_toolsets")[platform] = sorted(plugin_keys)
    _cfg_section(config, "known_builtin_toolsets")[platform] = sorted(_configurable_keys())
    agent_cfg = config.get("agent")
    newly_enabled = enabled_toolset_keys - preserved_entries
    if isinstance(agent_cfg, dict) and agent_cfg.get("disabled_toolsets") and newly_enabled:
        from agent.skill_utils import parse_config_string_list
        parsed_disabled = parse_config_string_list(agent_cfg["disabled_toolsets"])
        remaining = [ts for ts in parsed_disabled if ts not in newly_enabled]
        if remaining != parsed_disabled:
            agent_cfg["disabled_toolsets"] = remaining
    save_config(config)


def _provider_env_ready(provider: dict) -> bool:
    """True when every env var a provider row declares is set (trivially true for no-key rows)."""
    return all(get_env_value(e["key"]) for e in provider.get("env_vars", []))


def _toolset_has_keys(ts_key: str, config: dict = None, *, force_fresh: bool = False, features=None) -> bool:
    """Check direct vendor prerequisites for a toolset."""
    config = load_config() if config is None else config
    if ts_key == "vision":
        try:
            from agent.auxiliary_client import resolve_vision_provider_client
            return resolve_vision_provider_client()[1] is not None
        except Exception:
            return False
    cat = TOOL_CATEGORIES.get(ts_key)
    if cat:
        return any(_provider_env_ready(p) for p in _visible_providers(cat, config, force_fresh=force_fresh))
    return all(get_env_value(var) for var, _ in TOOLSET_ENV_REQUIREMENTS.get(ts_key, []))


logger = logging.getLogger(__name__)

from arkos_cli.tool_providers import _visible_providers
