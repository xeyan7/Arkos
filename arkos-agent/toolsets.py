"""Toolset helpers: get/resolve/validate named tool groups (static TOOLSETS + registry-registered)."""

from typing import Dict, List, Any, Set, Optional, Tuple


_ARKOS_CORE_TOOLS = [
    "web_search", "web_extract",
    "terminal", "process_manage",
    "read_file", "write_file", "patch", "search_files",
    "vision_analyze", "image_generate",
    "skills_list", "skill_view", "skill_manage",
    "browser_navigate", "browser_snapshot", "browser_click",
    "browser_type", "browser_scroll", "browser_back",
    "browser_press", "browser_get_images",
    "browser_vision", "browser_console", "browser_cdp", "browser_dialog",
    "browser_exec",
    "text_to_speech",
    "todo_list", "memory",
    "session_search",
    "clarify",
    "execute_code", "delegate_task",
    "cronjob_manage",
    "ha_list_entities", "ha_get_state", "ha_list_services", "ha_call_service",
    "kanban_show", "kanban_list",
    "kanban_complete", "kanban_block", "kanban_request_review",
    "kanban_request_changes",
    "kanban_heartbeat",
    "kanban_comment", "kanban_create", "kanban_link",
    "kanban_unblock",
    "kanban_attach", "kanban_attach_url", "kanban_attachments",
    "computer_use",
]

_ARKOS_WEBHOOK_SAFE_TOOLS = ["web_search", "web_extract", "vision_analyze", "clarify"]
_HA_TOOLS = ["ha_list_entities", "ha_get_state", "ha_list_services", "ha_call_service"]
_FEISHU_TOOLS = [
    "feishu_doc_read", "feishu_drive_list_comments", "feishu_drive_list_comment_replies",
    "feishu_drive_reply_comment", "feishu_drive_add_comment",
]
_YUANBAO_TOOLS = ["yb_query_group_info", "yb_query_group_members", "yb_send_dm", "yb_search_sticker", "yb_send_sticker"]


def _ts(description, tools=(), includes=(), **extra):
    """One TOOLSETS entry (fresh lists per entry; extra keys such as posture pass through)."""
    return {"description": description, "tools": list(tools), "includes": list(includes), **extra}


def _bundle(description, extras=()):
    """A `arkos-*` platform bundle: the shared core tools plus optional platform extras."""
    return _ts(description, _ARKOS_CORE_TOOLS + list(extras))


def _core_without(*excluded, kanban=True):
    """_ARKOS_CORE_TOOLS minus *excluded* (and, unless kanban=True, every kanban_* tool); order preserved."""
    return [t for t in _ARKOS_CORE_TOOLS if t not in excluded and (kanban or not t.startswith("kanban_"))]


_CODING_TOOLS = _core_without("image_generate", "text_to_speech", "cronjob_manage", "computer_use", *_HA_TOOLS, kanban=False)

TOOLSETS = {
    "web": _ts("Web research and content extraction tools", ["web_search", "web_extract"]),
    "search": _ts("Web search only (no content extraction/scraping)", ["web_search"]),
    "x_search": _ts(
        "Search X (Twitter) posts and threads via xAI's built-in x_search Responses "
        "tool. Read-only public X discovery; use the xurl skill for authenticated X "
        "API reads and account actions. Available when xAI credentials are configured "
        "(SuperGrok OAuth or XAI_API_KEY). Off by default; enable in `arkos tools` → "
        "X (Twitter) Search.",
        ["x_search"],
    ),
    "vision": _ts("Image analysis and vision tools", ["vision_analyze"]),
    "video": _ts("Video analysis and understanding tools (opt-in, not in default toolset)", ["video_analyze"]),
    "image_gen": _ts("Creative generation tools (images)", ["image_generate"]),
    "video_gen": _ts(
        "Video generation tools. Single ``video_generate`` tool covers text-to-video "
        "(prompt only) and image-to-video (prompt + image_url), plus "
        "reference-to-video. Provider-specific edit/extend workflows may appear as "
        "separate tools. Configure via ``arkos tools`` → Video Generation.",
        ["video_generate", "xai_video_edit", "xai_video_extend"],
    ),
    "computer_use": _ts(
        "Background desktop control via cua-driver (macOS/Windows/Linux) — "
        "screenshots, mouse, keyboard, scroll, drag. Does NOT steal the user's cursor "
        "or keyboard focus. Works with any tool-capable model.",
        ["computer_use"],
    ),
    "terminal": _ts("Terminal/command execution and process management tools", ["terminal", "process_manage"]),
    "skills": _ts(
        "Access, create, edit, and manage skill documents with specialized "
        "instructions and knowledge",
        ["skills_list", "skill_view", "skill_manage"],
    ),
    "browser": _ts(
        "Browser automation for web interaction (navigate, click, type, scroll, "
        "iframes, hold-click)",
        [t for t in _ARKOS_CORE_TOOLS if t.startswith("browser_")],
    ),
    "cronjob": _ts(
        "Cronjob management tool - create, list, update, pause, resume, remove, and "
        "trigger scheduled tasks",
        ["cronjob_manage"],
    ),
    "file": _ts(
        "File manipulation tools: read, write, patch (with fuzzy matching), and "
        "search (content + files)",
        ["read_file", "write_file", "patch", "search_files"],
    ),
    "tts": _ts("Text-to-speech: convert text to audio with Edge TTS (free), ElevenLabs, OpenAI, or xAI", ["text_to_speech"]),
    "todo": _ts("Task planning and tracking for multi-step work", ["todo_list"]),
    "memory": _ts("Persistent memory across sessions (personal notes + user profile)", ["memory"]),
    "context_engine": _ts("Runtime tools exposed by the active context engine"),
    "session_search": _ts("Search and recall past conversations with summarization", ["session_search"]),
    "project": _ts("Desktop Projects — create/switch named workspaces (GUI sessions only)", ["desktop_project"]),
    "bot_room": _ts("Verified text-only Group Chat turn capabilities"),

    "desktop_ui": _ts(
        "Desktop GUI affordances — in-app terminal/browser panes, pane focus, "
        "reactions (GUI sessions only)",
        ["read_terminal", "close_terminal", "desktop_preview", "drive_preview",
         "annotate_preview", "read_window_below", "focus_pane", "react_to_message",
         "setup_mcp", "gui_tour", "show_tip"],
    ),
    "clarify": _ts("Ask the user clarifying questions (multiple-choice or open-ended)", ["clarify"]),
    "code_execution": _ts("Run Python scripts that call tools programmatically (reduces LLM round trips)", ["execute_code"]),
    "delegation": _ts("Spawn subagents with isolated context for complex subtasks", ["delegate_task"]),
    "homeassistant": _ts("Home Assistant smart home control and monitoring", _HA_TOOLS),
    "kanban": _ts(
        "Kanban multi-agent coordination — only active when the agent is spawned by "
        "the kanban dispatcher (ARKOS_KANBAN_TASK env set). The dispatcher runs "
        "inside the gateway by default; see `kanban.dispatch_in_gateway` in "
        "config.yaml. Lets workers mark tasks done with structured handoffs, enter "
        "first-class review (request_review — not a block), return review changes, "
        "block for human input, heartbeat during long ops, comment on threads, attach "
        "files, and (for orchestrators) list, unblock, and fan out tasks.",
        [t for t in _ARKOS_CORE_TOOLS if t.startswith("kanban_")],
    ),
    "discord": _ts("Discord read and participate tools (fetch messages, search members, create threads)", ["discord"]),
    "discord_admin": _ts("Discord server management (list channels/roles, pin messages, assign roles)", ["discord_admin"]),
    "yuanbao": _ts("Yuanbao platform tools - group info, member queries, DM, stickers", _YUANBAO_TOOLS),
    "feishu_doc": _ts("Read Feishu/Lark document content", ["feishu_doc_read"]),
    "feishu_drive": _ts("Feishu/Lark document comment operations (list, reply, add)", _FEISHU_TOOLS[1:]),
    "spotify": _ts(
        "Native Spotify playback, search, playlist, album, and library tools",
        ["spotify_playback", "spotify_devices", "spotify_queue", "spotify_search",
         "spotify_playlists", "spotify_albums", "spotify_library"],
    ),

    "debugging": _ts("Debugging and troubleshooting toolkit", ["terminal", "process_manage"], includes=["web", "file"]),
    "safe": _ts("Safe toolkit without terminal access", [], includes=["web", "vision", "image_gen"]),

    "coding": _ts(
        "Coding-focused toolset: files, terminal, search, web docs, skills, todo, "
        "delegate, vision, browser",
        _CODING_TOOLS,
        posture=True,
    ),

    "arkos-acp": _ts(
        "Editor integration (VS Code, Zed, JetBrains) — coding-focused tools without "
        "messaging, audio, or clarify UI",
        [t for t in _CODING_TOOLS if t != "clarify"],
    ),
    "arkos-api-server": _ts(
        "OpenAI-compatible API server — full agent tools accessible via HTTP (no "
        "interactive UI tools like clarify or send_message)",
        _core_without("text_to_speech", "clarify", "computer_use", kanban=False),
    ),
    "arkos-cli": _bundle("Full interactive CLI toolset - all default tools plus cronjob management"),

    "arkos-cron": _bundle("Default cron toolset - same core tools as arkos-cli; gated by `arkos tools`"),
    "arkos-telegram": _bundle("Telegram bot toolset - full access for personal use (terminal has safety checks)"),
    "arkos-discord": _bundle(
        "Discord bot toolset - full access (terminal has safety checks via dangerous "
        "command approval)",
        ["discord", "discord_admin"],
    ),
    "arkos-whatsapp": _bundle("WhatsApp bot toolset - similar to Telegram (personal messaging, more trusted)"),
    "arkos-slack": _bundle("Slack bot toolset - full access for workspace use (terminal has safety checks)"),
    "arkos-signal": _bundle("Signal bot toolset - encrypted messaging platform (full access)"),
    "arkos-bluebubbles": _bundle("BlueBubbles iMessage bot toolset - Apple iMessage via local BlueBubbles server"),
    "arkos-homeassistant": _bundle("Home Assistant bot toolset - smart home event monitoring and control"),
    "arkos-email": _bundle("Email bot toolset - interact with Arkos via email (IMAP/SMTP)"),
    "arkos-mattermost": _bundle("Mattermost bot toolset - self-hosted team messaging (full access)"),
    "arkos-matrix": _bundle("Matrix bot toolset - decentralized encrypted messaging (full access)"),
    "arkos-dingtalk": _bundle("DingTalk bot toolset - enterprise messaging platform (full access)"),
    "arkos-feishu": _bundle("Feishu/Lark bot toolset - enterprise messaging via Feishu/Lark (full access)", _FEISHU_TOOLS),
    "arkos-weixin": _bundle("Weixin bot toolset - personal WeChat messaging via iLink (full access)"),
    "arkos-qqbot": _bundle("QQBot toolset - QQ messaging via Official Bot API v2 (full access)"),
    "arkos-wecom": _bundle("WeCom bot toolset - enterprise WeChat messaging (full access)"),
    "arkos-wecom-callback": _bundle("WeCom callback toolset - enterprise self-built app messaging (full access)"),
    "arkos-yuanbao": {
        "description": "Yuanbao Bot 元宝消息平台工具集 - 群信息、成员查询、私聊、贴纸表情",
        "tools": _ARKOS_CORE_TOOLS + _YUANBAO_TOOLS,
        "module": "tools.yuanbao_tools",
        "includes": [],
    },
    "arkos-sms": _bundle("SMS bot toolset - interact with Arkos via SMS (Twilio)"),
    "arkos-webhook": _ts("Webhook toolset - receive and process external webhook events", _ARKOS_WEBHOOK_SAFE_TOOLS),
    "arkos-gateway": _ts(
        "Gateway toolset - union of all messaging platform tools",
        [],
        includes=[
            "arkos-telegram", "arkos-discord", "arkos-whatsapp", "arkos-slack",
            "arkos-signal", "arkos-bluebubbles", "arkos-homeassistant", "arkos-email",
            "arkos-sms", "arkos-mattermost", "arkos-matrix", "arkos-dingtalk",
            "arkos-feishu", "arkos-wecom", "arkos-wecom-callback", "arkos-weixin",
            "arkos-qqbot", "arkos-webhook", "arkos-yuanbao",
        ],
    ),
}

_ARKOS_CORE_TOOLS = _ARKOS_CORE_TOOLS
_ARKOS_WEBHOOK_SAFE_TOOLS = _ARKOS_WEBHOOK_SAFE_TOOLS
for _k in list(TOOLSETS):
    if _k.startswith("arkos-"):
        _arkos_k = "arkos-" + _k[6:]
        _entry = dict(TOOLSETS[_k])
        _entry["includes"] = ["arkos-" + inc[6:] if inc.startswith("arkos-") else inc for inc in _entry.get("includes", [])]
        TOOLSETS[_arkos_k] = _entry


def _registry():
    """Live tool registry, or None when tools.registry can't be imported."""
    try:
        from tools.registry import registry
        return registry
    except Exception:
        return None


def _registry_call(method: str, default):
    """registry.<method>() or *default* when the registry is unavailable or the call fails."""
    try:
        return getattr(_registry(), method)()
    except Exception:
        return default


def _registry_generation() -> Tuple[int, int]:
    reg = _registry()
    return (id(reg), getattr(reg, "_generation", 0)) if reg is not None else (0, 0)


def get_toolset(name: str, *, include_registry: bool = True) -> Optional[Dict[str, Any]]:
    """Toolset definition, or None if unknown.

    include_registry=True merges plugin/overlay tools registered into this toolset
    and resolves registry-only (plugin/MCP) toolsets and aliases; False returns a
    copy of the static TOOLSETS entry only, so platform reverse-mapping is
    unaffected by registry additions.

    Args: name (str): Name of the toolset include_registry (bool): When True (default), merge in tools that
    plugins/overlays registered into this toolset via the registry. Platform reverse-mapping in
    ``_get_platform_tools`` uses False so that a tool registered into a toolset but absent from a platform's
    static composite does not drop the whole toolset from inference..
    """
    toolset = TOOLSETS.get(name)
    if not include_registry:
        return {**toolset, "tools": list(toolset.get("tools", [])), "includes": list(toolset.get("includes", []))} if toolset else None

    registry = _registry()
    if registry is None:
        return toolset if toolset else None

    if toolset:
        merged_tools = set(toolset.get("tools", [])) | set(registry.get_tool_names_for_toolset(name))
        alias_target = registry.get_toolset_alias_target(name)
        if alias_target and alias_target != name:
            merged_tools |= set(registry.get_tool_names_for_toolset(alias_target))
        return {**toolset, "tools": sorted(merged_tools)}

    if name in _get_plugin_toolset_names():
        registry_toolset = name
        alias = _display_alias(name, _get_registry_toolset_aliases())
        description = f"MCP server '{alias}' tools" if alias else f"Plugin toolset: {name}"
    else:
        registry_toolset = registry.get_toolset_alias_target(name)
        if not registry_toolset:
            return None
        description = f"MCP server '{name}' tools"
    return {"description": description, "tools": registry.get_tool_names_for_toolset(registry_toolset), "includes": []}


def bundle_non_core_tools(toolset_name: str) -> Set[str]:
    """A bundle's tools minus _ARKOS_CORE_TOOLS (one level of includes).

    Disabling a `core + extras` bundle must not strip the core tools every other
    toolset shares. One `includes` pass suffices (only arkos-gateway nests
    bundles). Unknown names: full resolution minus core.
    """
    core = set(_ARKOS_CORE_TOOLS)
    ts_def = get_toolset(toolset_name)
    if not (ts_def and "tools" in ts_def):
        return set(resolve_toolset(toolset_name)) - core
    to_remove = set(ts_def["tools"])
    for inc_def in map(get_toolset, ts_def.get("includes", [])):
        if inc_def and "tools" in inc_def:
            to_remove.update(inc_def["tools"])
    return to_remove - core


_resolve_toolset_memo: Dict[Tuple[str, bool, int, int], List[str]] = {}


def _plugin_platform_bundle(name: str) -> List[str]:
    """Implicit `arkos-<platform>` bundle for a registered plugin platform: core
    tools plus whatever the plugin registered under the platform name. [] otherwise."""
    if not name.startswith("arkos-"):
        return []
    platform_name = name[len("arkos-"):]
    try:
        from gateway.platform_registry import platform_registry
        if not platform_registry.is_registered(platform_name):
            return []
    except Exception:
        return []
    tools = set(_ARKOS_CORE_TOOLS)
    try:
        tools.update(e.name for e in _registry_call("get_all_entries", ()) if e.toolset == platform_name)
    except Exception:
        pass
    return list(tools)


def resolve_toolset(name: str, visited: Set[str] = None, *, include_registry: bool = True) -> List[str]:
    """Recursively resolve a toolset (and its includes) to a sorted tool-name list.
    include_registry=False resolves the static TOOLSETS view only.

    Args: name (str): Name of the toolset to resolve visited (Set[str]): Set of already visited toolsets
    (for cycle detection) include_registry (bool): When True (default), include tools that plugins/overlays
    registered into a toolset. Platform reverse-mapping uses False so a registry-added tool cannot drop the
    whole toolset from inference (and ``_get_platform_tools``).
    """
    external_call = visited is None
    if external_call:
        memo_key = (name, include_registry, *_registry_generation())
        cached = _resolve_toolset_memo.get(memo_key)
        if cached is not None:
            return list(cached)
        visited = set()

    if name in {"all", "*"}:
        all_tools: Set[str] = set()
        for toolset_name in get_toolset_names():
            all_tools.update(resolve_toolset(toolset_name, visited.copy(), include_registry=include_registry))
        return sorted(all_tools)

    if name in visited:
        return []
    visited.add(name)

    toolset = get_toolset(name, include_registry=include_registry)
    if not toolset:
        return _plugin_platform_bundle(name) if include_registry else []

    tools = set(toolset.get("tools", []))
    for included_name in toolset.get("includes", []):
        tools.update(resolve_toolset(included_name, visited, include_registry=include_registry))

    result = sorted(tools)
    if external_call:
        if len(_resolve_toolset_memo) >= 256:
            _resolve_toolset_memo.clear()
        _resolve_toolset_memo[memo_key] = list(result)
    return result


def _get_plugin_toolset_names() -> Set[str]:
    """Registry toolset names absent from the static TOOLSETS dict."""
    return {n for n in _registry_call("get_registered_toolset_names", ()) if n not in TOOLSETS}


def _get_registry_toolset_aliases() -> Dict[str, str]:
    return _registry_call("get_registered_toolset_aliases", {})


def _display_alias(ts_name: str, aliases: Dict[str, str]) -> Optional[str]:
    """First non-static alias pointing at *ts_name*, or None."""
    return next((a for a, canonical in aliases.items() if canonical == ts_name and a not in TOOLSETS), None)


def _plugin_display_names() -> List[str]:
    """Plugin toolset names, shown under their first non-static alias when one exists."""
    aliases = _get_registry_toolset_aliases()
    return [_display_alias(n, aliases) or n for n in _get_plugin_toolset_names()]


def get_all_toolsets() -> Dict[str, Dict[str, Any]]:
    """All toolset definitions: static plus plugin-registered."""
    result = dict(TOOLSETS)
    aliases = _get_registry_toolset_aliases()
    for display_name in _plugin_display_names():
        toolset = None if display_name in result else get_toolset(display_name)
        if toolset:
            result[display_name] = toolset
    for name in TOOLSETS.keys() & aliases.keys():
        result[name] = get_toolset(name) or result[name]
    return result


def get_toolset_names() -> List[str]:
    """Sorted names of all toolsets (static + plugin), excluding aliases."""
    return sorted(set(TOOLSETS.keys()) | set(_plugin_display_names()))


def validate_toolset(name: str) -> bool:
    return (name in {"all", "*"} or name in TOOLSETS
            or name in _get_plugin_toolset_names() or name in _get_registry_toolset_aliases())


def create_custom_toolset(name: str, description: str, tools: List[str] = None, includes: List[str] = None) -> None:
    """Register a runtime toolset in TOOLSETS."""
    TOOLSETS[name] = _ts(description, tools or [], includes or [])


def get_toolset_info(name: str) -> Dict[str, Any]:
    """Toolset definition plus its resolved tools, or None if unknown."""
    toolset = get_toolset(name)
    if not toolset:
        return None
    resolved_tools = resolve_toolset(name)
    return {
        "name": name, "description": toolset["description"],
        "direct_tools": toolset["tools"], "includes": toolset["includes"],
        "resolved_tools": resolved_tools, "tool_count": len(resolved_tools),
        "is_composite": bool(toolset["includes"]),
    }



def resolve_multiple_toolsets(toolset_names: List[str]) -> List[str]:
    """
    Resolve multiple toolsets and combine their tools.

    Args:
        toolset_names (List[str]): List of toolset names to resolve

    Returns:
        List[str]: Combined list of all tool names (deduplicated)
    """
    all_tools = set()

    for name in toolset_names:
        tools = resolve_toolset(name)
        all_tools.update(tools)

    return sorted(all_tools)
