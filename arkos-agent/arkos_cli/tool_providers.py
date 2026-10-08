"""Headless tool-provider metadata, availability, catalogs, and configuration selection."""

from __future__ import annotations


import importlib


import logging


from functools import partial


from typing import Callable, Optional


from arkos_cli.config import cfg_get, get_env_value, load_config, save_config, save_env_value


def _plugin_registry(module: str):
    """Import a plugin registry module after plugin discovery; ``None`` on any failure."""
    try:
        registry = importlib.import_module(module)
        from arkos_cli.plugins import _ensure_plugins_discovered

        _ensure_plugins_discovered()
        return registry
    except Exception:
        return None


def _plugin_provider_rows(
    registry_module: str, marker_keys: tuple[str, ...], *, require_name: bool = True, skip_builtin: bool = False,
    flatten_variants: bool = False) -> list[dict]:
    """Picker-row dicts (TOOL_CATEGORIES-shaped) for a plugin registry's providers.
    ``marker_keys`` are all set to the registry name so downstream config/model-picker code routes
    through the registry. ``skip_builtin`` drops names shadowing ``_BUILTIN_NAMES``;
    ``flatten_variants`` expands a schema's tier ``variants`` into separate rows sharing one backend
    name, distinguished by ``web_tier``."""
    registry = _plugin_registry(registry_module)
    if registry is None:
        return []
    try:
        providers = registry.list_providers()
        builtin = registry._BUILTIN_NAMES if skip_builtin else frozenset()
    except Exception:
        return []

    rows: list[dict] = []
    for provider in providers:
        if require_name:
            name = getattr(provider, "name", None)
            if not name or (skip_builtin and name.lower().strip() in builtin):
                continue
        try:
            schema = provider.get_setup_schema()
        except Exception:
            continue
        if not isinstance(schema, dict):
            continue
        if not require_name:
            name = provider.name
        entries = [schema]
        if flatten_variants:
            entries += [v for v in (schema.get("variants") or []) if isinstance(v, dict)]
        for entry in entries:
            row = {"name": entry.get("name", provider.display_name), "badge": entry.get("badge", ""),
                   "tag": entry.get("tag", ""), "env_vars": entry.get("env_vars", [])}
            row.update({key: name for key in marker_keys})
            if flatten_variants and entry.get("web_tier"):
                row["web_tier"] = entry["web_tier"]
            if entry.get("post_setup"):
                row["post_setup"] = entry["post_setup"]
            rows.append(row)
    return rows


_PLUGIN_PROVIDER_ROW_SPECS = {
    "image_gen": ("agent.image_gen_registry", ("image_gen_plugin_name",), {"require_name": False}),
    "video_gen": ("agent.video_gen_registry", ("video_gen_plugin_name",), {"require_name": False}),
    "web": ("agent.web_search_registry", ("web_backend", "web_search_plugin_name"), {"flatten_variants": True}),
    "browser": ("agent.browser_registry", ("browser_provider", "browser_plugin_name"), {}),
    "tts": ("agent.tts_registry", ("tts_provider", "tts_plugin_name"), {"skip_builtin": True})}


def _plugin_rows_for(category: str) -> list[dict]:
    """Picker rows for the plugin-registered providers of one ``_PLUGIN_PROVIDER_ROW_SPECS`` category."""
    module, markers, kwargs = _PLUGIN_PROVIDER_ROW_SPECS[category]
    return _plugin_provider_rows(module, markers, **kwargs)


_plugin_image_gen_providers, _plugin_video_gen_providers, _plugin_web_search_providers, \
    _plugin_browser_providers, _plugin_tts_providers = (
        partial(_plugin_rows_for, cat) for cat in ("image_gen", "video_gen", "web", "browser", "tts"))


def web_provider_capabilities(backend: str) -> list:
    """Capabilities (``search`` / ``extract``) a web backend supports, per the registry provider instance.
    Lets the Capabilities GUI offer ``web.search_backend`` / ``web.extract_backend`` only where it makes
    sense (ddgs and brave-free are search-only). Unknown backend or registry failure -> both."""
    try:
        from agent.web_search_registry import get_provider

        provider = get_provider(backend)
        if provider is not None:
            return [cap for cap, supported in (("search", provider.supports_search()),
                                               ("extract", provider.supports_extract())) if supported]
    except Exception:
        pass
    return ["search", "extract"]


_PLUGIN_ROW_BUILDERS = {
    "Image Generation": _plugin_image_gen_providers,
    "Video Generation": _plugin_video_gen_providers,
    "Web Search & Extract": _plugin_web_search_providers,
    "Browser Automation": _plugin_browser_providers,
    "Text-to-Speech": _plugin_tts_providers}


def _visible_providers(cat: dict, config: dict, *, force_fresh: bool = False, features=None) -> list[dict]:
    """Bundled and plugin vendor rows available for configuration."""
    visible = list(cat.get("providers", []))
    builder = _PLUGIN_ROW_BUILDERS.get(cat.get("name"))
    if builder is not None:
        visible.extend(builder())
    return visible


def provider_readiness_status(provider: dict, config: dict, *, features=None, is_active: Optional[bool] = None) -> str:
    """Honest readiness state for a provider picker row.
    ``features`` is retained for compatibility with setup callers. ``is_active`` is the completed-setup fallback
    for post_setup hooks with no registered installed-check (selecting a row runs its hook)."""
    from arkos_cli.tool_dependencies import _POST_SETUP_READY
    from arkos_cli.tool_configuration import _provider_env_ready, _xai_credentials_present

    if provider.get("env_vars", []):
        return "ready" if _provider_env_ready(provider) else "needs_keys"


    post_setup = provider.get("post_setup")
    if post_setup:
        if post_setup == "xai_grok":
            return "ready" if _xai_credentials_present() else "needs_auth"
        predicate = _POST_SETUP_READY.get(post_setup)
        if predicate is not None:
            try:
                return "ready" if predicate() else "needs_setup"
            except Exception:
                return "ready"
        if is_active is None:
            is_active = _is_provider_active(provider, config)
        return "ready" if is_active else "needs_setup"

    return "ready"


def _web_tier_matches(provider: dict, config: dict) -> bool:
    """True when a web picker row's tier matches the configured tier (``web.provider_tier.<backend>``).
    Tiered rows (Exa/Parallel Free vs Paid) share one ``web_backend`` and differ only in ``web_tier``.
    No ``web_tier`` on the row → matches; configured tier set → must equal the row's tier; unset →
    "auto": paid when the row's key is present, free otherwise (highlight the row the runtime would
    actually use)."""
    row_tier = provider.get("web_tier")
    if not row_tier:
        return True
    web_cfg = config.get("web") if isinstance(config.get("web"), dict) else {}
    tiers = web_cfg.get("provider_tier") if isinstance(web_cfg.get("provider_tier"), dict) else {}
    configured = str(tiers.get(provider["web_backend"], "") or "").lower().strip()
    if configured in ("free", "paid"):
        return configured == row_tier
    try:
        from agent.web_search_provider import get_provider_env

        key_var = {"exa": "EXA_API_KEY", "parallel": "PARALLEL_API_KEY"}.get(provider["web_backend"])
        has_key = bool(get_provider_env(key_var)) if key_var else False
    except Exception:
        has_key = False
    return row_tier == ("paid" if has_key else "free")


def _has_marker(provider: dict, marker: str) -> bool:
    """``browser_provider`` is a membership test (a local row carries ``browser_provider: ""``); every other
    marker is a truthiness test."""
    return marker in provider if marker == "browser_provider" else bool(provider.get(marker))


def _browser_use_default_active(config: dict) -> bool:
    """``browser.backend`` unset: Browser Use mode is the default, so the row is active whenever the
    effective mode resolves on (legacy direct-API cloud config, or CLI runnable and no Camofox)."""
    browser_cfg = config.get("browser") if isinstance(config, dict) else None
    try:
        from tools.browser_use_cli import _find_cli, is_legacy_browser_use_cloud_config

        if is_legacy_browser_use_cloud_config(browser_cfg or {}):
            return True
        try:
            from tools.browser_camofox import is_camofox_mode

            if is_camofox_mode():
                return False
        except Exception:
            pass
        return _find_cli() is not None
    except Exception:
        return False


def _browser_provider_active(provider: dict, config: dict) -> bool:
    if provider["browser_provider"] != cfg_get(config, "browser", "cloud_provider"):
        return False
    if provider.get("browser_engine"):
        engine = str(cfg_get(config, "browser", "engine") or "auto").strip().lower()
        return engine == provider["browser_engine"]
    return True


def _browser_backend_active(provider: dict, config: dict) -> bool:
    backend = cfg_get(config, "browser", "backend")
    if backend is False:
        backend = "off"
    if backend == provider["browser_backend"]:
        return True
    if backend:
        return False
    if provider["browser_backend"] != "browser-use":
        return False
    return _browser_use_default_active(config)


def _imagegen_backend_active(provider: dict, config: dict) -> bool:
    image_cfg = config.get("image_gen", {})
    return (
        isinstance(image_cfg, dict)
        and provider["imagegen_backend"] == "fal"
        and image_cfg.get("provider") in {None, "", "fal"}
)


_ACTIVE_CHECKS: tuple[tuple[str, Callable[[dict, dict], bool]], ...] = (
    ("tts_provider", lambda p, c: cfg_get(c, "tts", "provider") == p["tts_provider"]),
    ("stt_provider", lambda p, c: (cfg_get(c, "stt", "provider") or "local") == p["stt_provider"]),
    ("browser_provider", _browser_provider_active),
    ("browser_backend", _browser_backend_active),
    ("web_backend", lambda p, c: cfg_get(c, "web", "backend") == p["web_backend"] and _web_tier_matches(p, c)),
    ("computer_use_backend", lambda p, c: cfg_get(c, "computer_use", "backend") == p["computer_use_backend"]),
    ("imagegen_backend", _imagegen_backend_active))


def _is_provider_active(provider: dict, config: dict, *, force_fresh: bool = False) -> bool:
    """Check if a provider entry matches the currently active config."""
    for section in ("image_gen", "video_gen"):
        plugin_name = provider.get(f"{section}_plugin_name")
        if plugin_name:
            gen_cfg = config.get(section, {})
            if not (isinstance(gen_cfg, dict) and gen_cfg.get("provider") == plugin_name):
                return False
            return True


    for marker, check in _ACTIVE_CHECKS:
        if _has_marker(provider, marker):
            return check(provider, config)
    return False


def _detect_active_provider_index(providers: list, config: dict, *, force_fresh: bool = False) -> int:
    """Return the index of the currently active provider, or 0."""
    from arkos_cli.tool_configuration import _provider_env_ready

    for i, p in enumerate(providers):
        if _is_provider_active(p, config, force_fresh=force_fresh):
            return i
        if p.get("env_vars", []) and _provider_env_ready(p):
            return i
    return 0


def _fal_model_catalog():
    """Lazy-load the FAL model catalog."""
    from tools.image_generation_catalog import FAL_MODELS, DEFAULT_MODEL
    return FAL_MODELS, DEFAULT_MODEL


IMAGEGEN_BACKENDS = {
    "fal": {"display": "FAL.ai", "config_key": "image_gen", "catalog_fn": _fal_model_catalog}}


def _plugin_model_catalog(registry_module: str, plugin_name: str):
    """``(catalog_dict, default_model_id)`` for a plugin provider; ``catalog_dict`` is shaped like the legacy
    ``FAL_MODELS`` table so the picker path is shared. ``({}, None)`` if unregistered or no models."""
    registry = _plugin_registry(registry_module)
    try:
        provider = registry.get_provider(plugin_name)
        models = provider.list_models() or []
        default = provider.default_model()
    except Exception:
        return {}, None
    return {m["id"]: m for m in models if isinstance(m, dict) and "id" in m}, default


_plugin_image_gen_catalog = partial(_plugin_model_catalog, "agent.image_gen_registry")


_plugin_video_gen_catalog = partial(_plugin_model_catalog, "agent.video_gen_registry")


def _select_into(config: dict, section: str, key: str, vendor: str) -> dict:
    """Persist a direct vendor selection."""
    cfg = config.setdefault(section, {})
    cfg[key] = vendor
    cfg.pop("use_gateway", None)
    return cfg


STT_MODEL_CATALOG = {
    "local": ["base", "tiny", "small", "medium", "large-v3"],
    "groq": ["whisper-large-v3-turbo", "whisper-large-v3", "distil-whisper-large-v3-en"],
    "openai": ["whisper-1", "gpt-4o-mini-transcribe", "gpt-4o-transcribe", "gpt-transcribe"],
    "elevenlabs": ["scribe_v2", "scribe_v1"]}


_PROVIDER_MARKER_SECTIONS = {
    "tts_provider": "tts", "stt_provider": "stt", "browser_provider": "browser", "web_backend": "web",
    "image_gen_plugin_name": "image_gen", "imagegen_backend": "image_gen", "video_gen_plugin_name": "video_gen",
}


def _write_provider_config(provider: dict, config: dict) -> None:
    """Persist direct vendor selections without prompting for credentials."""
    from arkos_cli.tool_configuration import TOOL_CATEGORIES

    for marker, section_key in (("tts_provider", "tts"), ("stt_provider", "stt")):
        if provider.get(marker):
            _select_into(config, section_key, 'provider', provider[marker])

    if "browser_provider" in provider:
        bp = provider["browser_provider"]
        if bp:
            _select_into(config, 'browser', 'cloud_provider', bp)
        else:
            config.setdefault("browser", {}).pop("use_gateway", None)
    if provider.get("browser_backend"):
        config.setdefault("browser", {})["backend"] = provider["browser_backend"]
    if provider.get("browser_engine"):
        config.setdefault("browser", {})["engine"] = provider["browser_engine"]

    if provider.get("web_backend"):
        web_cfg = _select_into(config, 'web', 'backend', provider['web_backend'])
        tier = provider.get("web_tier")
        tiers = web_cfg.setdefault("provider_tier", {}) if tier else web_cfg.get("provider_tier")
        if isinstance(tiers, dict):
            if tier:
                tiers[provider["web_backend"]] = tier
            else:
                tiers.pop(provider["web_backend"], None)

    if provider.get("computer_use_backend"):
        config.setdefault("computer_use", {})["backend"] = provider["computer_use_backend"]

    sections = [section_key for marker, section_key in _PROVIDER_MARKER_SECTIONS.items() if marker in provider]
    if not sections:
        sections = [cat_key for cat_key, cat in TOOL_CATEGORIES.items() if provider in cat.get("providers", [])][:1]
    for section_key in sections:
        if isinstance(config.get(section_key), dict):
            config[section_key].pop("use_gateway", None)


def apply_provider_selection(ts_key: str, provider_name: str, config: dict) -> None:
    """Non-interactively persist a provider selection for a toolset (config keys only — API keys, post-setup
    hooks, auth gating and model pickers are separate GUI endpoints). ``provider_name`` is resolved among
    :func:`_visible_providers` rows; raises ``KeyError`` for an unknown toolset or provider."""
    from arkos_cli.tool_configuration import TOOL_CATEGORIES

    cat = TOOL_CATEGORIES.get(ts_key)
    if cat is None:
        raise KeyError(f"Toolset has no configurable category: {ts_key}")

    providers = _visible_providers(cat, config, force_fresh=True)
    provider = next((p for p in providers if p.get("name") == provider_name), None)
    if provider is None:
        raise KeyError(f"Unknown provider {provider_name!r} for toolset {ts_key!r}")

    _write_provider_config(provider, config)

    selections = [
        ("image_gen", provider.get("image_gen_plugin_name")),
        ("video_gen", provider.get("video_gen_plugin_name")),
        ("image_gen", "fal" if provider.get('imagegen_backend') else None)]
    for section_key, vendor in selections:
        if vendor:
            _select_into(config, section_key, 'provider', vendor)

logger = logging.getLogger(__name__)
