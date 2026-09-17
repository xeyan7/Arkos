"""Table-driven config migration registry.

Each step is ``_migrate_to_N(results, quiet)``; the version gate and strict ascending order live
in :func:`run_migrations`. Every write goes through ``arkos_cli.config._persist_migration`` so a
step may only persist values that differ from the schema default (plus removals/renames).
"""

from __future__ import annotations

import copy
import functools
import re
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

SUPPORT_FLOOR_VERSION = 12


def support_floor_message() -> str:
    """Human-facing explanation shown when a config is below the floor."""
    from arkos_constants import display_arkos_home

    return (
        f"This config predates version {SUPPORT_FLOOR_VERSION} (~2 years old) "
        "and can no longer be auto-migrated. Back up "
        f"{display_arkos_home()}/config.yaml and run `arkos setup` to "
        f"regenerate, or manually set _config_version: {SUPPORT_FLOOR_VERSION} "
        "after reviewing the changelog.")


def _cfg():
    """Return the live ``arkos_cli.config`` module (lazy, cycle-free, monkeypatch-friendly)."""
    from arkos_cli import config

    return config


def read_raw_config():
    return _cfg().read_raw_config()


def _persist_migration(config):
    _cfg()._persist_migration(config)


def _dict_at(config: Dict[str, Any], key: str) -> Dict[str, Any]:
    """``config[key]`` when it is a mapping (same object, so writes alias), else a fresh ``{}``."""
    value = config.get(key)
    return value if isinstance(value, dict) else {}


def _commit(
    config: Dict[str, Any],
    results: Dict[str, Any],
    quiet: bool,
    added: Optional[str],
    message: Optional[str]) -> None:
    """Persist *config*, record *added* under ``config_added`` and print *message* unless quiet."""
    _persist_migration(config)
    if added:
        results["config_added"].append(added)
    if message and not quiet:
        print(message)


def _rewrite_key(
    results: Dict[str, Any],
    quiet: bool,
    *,
    section: str,
    key: str,
    match: Callable[[Any], bool],
    new: Any,
    added: str,
    message: str,
    extra_guard: Callable[[Dict[str, Any]], bool] = lambda _m: True,
    create_section: bool = False) -> None:
    """Rewrite ``<section>.<key>`` to *new* (None = delete) when ``match(current)`` holds; a
    missing section is skipped unless *create_section*."""
    config = read_raw_config()
    raw = config.get(section)
    if not isinstance(raw, dict):
        if not create_section:
            return
        raw = {}
    if match(raw.get(key)) and extra_guard(raw):
        if new is None:
            del raw[key]
        else:
            raw[key] = new
        config[section] = raw
        _commit(config, results, quiet, added, message)


def _rewrite_stale_default(*, old: Any, **kw: Any) -> Callable[[Dict[str, Any], bool], None]:
    """Step rewriting a key only while it still equals the OLD default — never clobbers a value
    the user customized; unset keys inherit the new default at read time."""
    return functools.partial(_rewrite_key, match=lambda cur: cur == old, **kw)


def _lower_is(word: str) -> Callable[[Any], bool]:
    return lambda cur: isinstance(cur, str) and cur.strip().lower() == word


def _migrate_to_12(results: Dict[str, Any], quiet: bool) -> None:
    _custom_provider_entry_to_provider_config = _cfg()._custom_provider_entry_to_provider_config

    config = read_raw_config()
    custom_list = config.get("custom_providers")
    if not (isinstance(custom_list, list) and custom_list):
        return
    providers_dict = _dict_at(config, "providers")
    migrated_count = 0
    for entry in custom_list:
        if not isinstance(entry, dict):
            continue
        old_name = entry.get("name", "")
        old_url = entry.get("base_url", "") or entry.get("url", "") or entry.get("api", "") or ""
        if not old_url:
            continue

        key = old_name.strip().lower().replace(" ", "-").replace("(", "").replace(")", "")
        key = re.sub(r"-{2,}", "-", key).strip("-")
        if not key:
            try:
                key = (urlparse(old_url).hostname or "endpoint").replace(".", "-")
            except Exception:
                key = f"endpoint-{migrated_count}"

        base_key = key
        suffix = migrated_count
        while key in providers_dict:
            key = f"{base_key}-{suffix}"
            suffix += 1

        new_entry = _custom_provider_entry_to_provider_config(entry, provider_key=key)
        if new_entry is None:
            continue
        if not old_name:
            new_entry.pop("name", None)
        if new_entry.get("api_key") in {"no-key", "no-key-required", ""}:
            new_entry.pop("api_key", None)

        providers_dict[key] = new_entry
        migrated_count += 1

    if migrated_count > 0:
        config["providers"] = providers_dict
        config.pop("custom_providers", None)
        _persist_migration(config)
        if not quiet:
            print(f"  ✓ Migrated {migrated_count} custom provider(s) to providers: section")
            for key in list(providers_dict.keys())[-migrated_count:]:
                print(f"    → {key}: {providers_dict[key].get('api', '')}")


def _migrate_to_13(results: Dict[str, Any], quiet: bool) -> None:
    _c = _cfg()
    for dead_var in ("LLM_MODEL", "OPENAI_MODEL"):
        try:
            if _c.get_env_value(dead_var):
                _c.save_env_value(dead_var, "")
                if not quiet:
                    print(f"  ✓ Cleared {dead_var} from .env (no longer used — config.yaml is source of truth)")
        except Exception:
            pass


_LOCAL_WHISPER_MODELS = frozenset({
    "tiny.en", "tiny", "base.en", "base", "small.en", "small",
    "medium.en", "medium", "large-v1", "large-v2", "large-v3",
    "large", "distil-large-v2", "distil-medium.en",
    "distil-small.en", "distil-large-v3", "distil-large-v3.5",
    "large-v3-turbo", "turbo"})


def _migrate_to_14(results: Dict[str, Any], quiet: bool) -> None:
    raw_stt = read_raw_config().get("stt", {})
    if not (isinstance(raw_stt, dict) and "model" in raw_stt):
        return
    legacy_model = raw_stt["model"]
    provider = raw_stt.get("provider", "local")
    config = read_raw_config()
    stt = config.get("stt", {})
    stt.pop("model", None)

    def _place(section: str) -> None:
        existing = raw_stt.get(section, {})
        if not isinstance(existing, dict) or "model" not in existing:
            stt.setdefault(section, {})["model"] = legacy_model

    if provider in {"local", "local_command"}:
        if legacy_model in _LOCAL_WHISPER_MODELS:
            _place("local")
    else:
        _place(provider)
    config["stt"] = stt
    _commit(
        config, results, quiet, None, "  ✓ Migrated legacy stt.model to provider-specific config")


def _migrate_to_16(results: Dict[str, Any], quiet: bool) -> None:
    config = read_raw_config()
    display = _dict_at(config, "display")
    old_overrides = display.get("tool_progress_overrides")
    if not (isinstance(old_overrides, dict) and old_overrides):
        return
    platforms = _dict_at(display, "platforms")
    for plat, mode in old_overrides.items():
        if plat not in platforms:
            platforms[plat] = {}
        if "tool_progress" not in platforms[plat]:
            platforms[plat]["tool_progress"] = mode
    display["platforms"] = platforms
    config["display"] = display
    migrated = ", ".join(f"{p}={m}" for p, m in old_overrides.items())
    _commit(
        config, results, quiet,
        "display.platforms (migrated from tool_progress_overrides)",
        f"  ✓ Migrated tool_progress_overrides → display.platforms: {migrated}")


def _migrate_to_17(results: Dict[str, Any], quiet: bool) -> None:
    config = read_raw_config()
    comp = config.get("compression", {})
    if not isinstance(comp, dict):
        return
    legacy = {k: comp.pop(f"summary_{k}", None) for k in ("model", "provider", "base_url")}
    migrated_keys = []
    for k, raw in legacy.items():
        val = str(raw).strip() if raw else ""
        if not val or (k == "provider" and val == "auto"):
            continue
        aux_comp = config.setdefault("auxiliary", {}).setdefault("compression", {})
        cur = aux_comp.get(k)
        if not cur or (k == "provider" and cur == "auto"):
            aux_comp[k] = val
            migrated_keys.append(f"{k}={raw}")
    if migrated_keys or any(v is not None for v in legacy.values()):
        config["compression"] = comp
        message = (
            "  ✓ Migrated compression.summary_* → auxiliary.compression: "
            f"{', '.join(migrated_keys)}"
            if migrated_keys else "  ✓ Removed unused compression.summary_* keys")
        _commit(config, results, quiet, None, message)


def _installed_user_plugins(disabled: set) -> List[str]:
    """Names of plugins under ``$ARKOS_HOME/plugins/`` with a manifest, minus *disabled*."""
    _c = _cfg()
    found: List[str] = []
    try:
        user_plugins_dir = _c.get_arkos_home() / "plugins"
        if user_plugins_dir.is_dir():
            for child in sorted(user_plugins_dir.iterdir()):
                if not child.is_dir():
                    continue
                manifest_file = child / "plugin.yaml"
                if not manifest_file.exists():
                    manifest_file = child / "plugin.yml"
                if not manifest_file.exists():
                    continue
                try:
                    with open(manifest_file, encoding="utf-8") as _mf:
                        manifest = _c.fast_safe_load(_mf) or {}
                except Exception:
                    manifest = {}
                name = manifest.get("name") or child.name
                if name not in disabled:
                    found.append(name)
    except Exception:
        return []
    return found


def _migrate_to_21(results: Dict[str, Any], quiet: bool) -> None:
    config = read_raw_config()
    plugins_cfg = _dict_at(config, "plugins")
    if "enabled" in plugins_cfg:
        return
    disabled = plugins_cfg.get("disabled", []) or []
    grandfathered = _installed_user_plugins(set(disabled) if isinstance(disabled, list) else set())
    plugins_cfg["enabled"] = grandfathered
    config["plugins"] = plugins_cfg
    message = (
        f"  ✓ Plugins now opt-in: grandfathered "
        f"{len(grandfathered)} existing plugin(s) into plugins.enabled"
        if grandfathered else
        "  ✓ Plugins now opt-in: no existing plugins to grandfather. "
        "Use `arkos plugins enable <name>` to activate.")
    _commit(
        config, results, quiet,
        f"plugins.enabled (opt-in allow-list, {len(grandfathered)} grandfathered)", message)


def _migrate_to_23(results: Dict[str, Any], quiet: bool) -> None:
    _c = _cfg()
    DEFAULT_CONFIG = _c.DEFAULT_CONFIG

    try:
        curator_dir = _c.get_arkos_home() / "logs" / "curator"
        curator_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        results["warnings"].append(f"Could not create {curator_dir}: {e}")

    config = read_raw_config()

    def _seed_missing(section: Dict[str, Any], defaults: Dict[str, Any]) -> List[str]:
        added = [k for k in defaults if k not in section]
        for k in added:
            section[k] = copy.deepcopy(defaults[k])
        return added

    raw_curator = _dict_at(config, "curator")
    added_curator = _seed_missing(raw_curator, DEFAULT_CONFIG.get("curator", {}))
    if added_curator:
        config["curator"] = raw_curator

    raw_aux = _dict_at(config, "auxiliary")
    raw_aux_curator = _dict_at(raw_aux, "curator")
    added_aux = _seed_missing(
        raw_aux_curator, DEFAULT_CONFIG.get("auxiliary", {}).get("curator", {}))
    if added_aux:
        raw_aux["curator"] = raw_aux_curator
        config["auxiliary"] = raw_aux

    if added_curator or added_aux:
        _persist_migration(config)
        for label, added in (("curator", added_curator), ("auxiliary.curator", added_aux)):
            if not added:
                continue
            results["config_added"].append(f"{label} ({len(added)} default key(s))")
            if not quiet:
                print(
                    f"  ✓ {'Curator' if label == 'curator' else label} settings now available "
                    f"({', '.join(added)}) — edit via `arkos config set`")


def _migrate_to_29(results: Dict[str, Any], quiet: bool) -> None:
    config = read_raw_config()
    touched = False
    for subsystem in ("memory", "skills"):
        sub = config.get(subsystem)
        if not isinstance(sub, dict) or "write_mode" not in sub:
            continue
        old = sub.pop("write_mode")
        old_norm = old.strip().lower() if isinstance(old, str) else old
        sub["write_approval"] = (old_norm == "approve")
        config[subsystem] = sub
        touched = True
        results["config_added"].append(
            f"{subsystem}.write_mode → write_approval={sub['write_approval']}")
    if touched:
        _commit(config, results, quiet, None,
                "  ✓ Renamed write_mode → write_approval (boolean gate)")




def _migrate_to_33(results: Dict[str, Any], quiet: bool) -> None:
    config = read_raw_config()
    raw_deleg = config.get("delegation")
    if not (isinstance(raw_deleg, dict) and "max_async_children" in raw_deleg):
        return
    old_async = raw_deleg.pop("max_async_children")
    try:
        old_async_i = int(old_async)
    except (TypeError, ValueError):
        old_async_i = None
    if old_async_i is not None and old_async_i > 3:
        try:
            cur_children = int(raw_deleg.get("max_concurrent_children", 3))
        except (TypeError, ValueError):
            cur_children = 3
        if old_async_i > cur_children:
            raw_deleg["max_concurrent_children"] = old_async_i
            results["config_added"].append(
                f"delegation.max_concurrent_children={old_async_i} "
                f"(folded from deprecated max_async_children)")
    config["delegation"] = raw_deleg
    _commit(
        config, results, quiet, None,
        "  ✓ Removed deprecated delegation.max_async_children — "
        "delegation.max_concurrent_children now caps background "
        "delegations too.")


def _migrate_to_34(results: Dict[str, Any], quiet: bool) -> None:
    from arkos_cli.personality import (
        available_personalities, normalize_personality_name, prompt_text, render_personality_prompt)

    config = read_raw_config()
    touched = False

    raw_display = config.get("display")
    old_name = ""
    if isinstance(raw_display, dict):
        old_name = normalize_personality_name(raw_display.get("personality", ""))
        if old_name:
            raw_display["personality"] = ""
            config["display"] = raw_display
            touched = True

    raw_agent = config.get("agent")
    scrubbed_text = False
    if isinstance(raw_agent, dict):
        manual = prompt_text(raw_agent.get("system_prompt", ""))
        if manual:
            rendered = {
                render_personality_prompt(defn) for defn in available_personalities(config).values()
            }
            if manual in rendered:
                raw_agent["system_prompt"] = ""
                config["agent"] = raw_agent
                touched = True
                scrubbed_text = True

    if not touched:
        return
    _commit(config, results, quiet, "display.personality=none (one-time reset)", None)
    if quiet:
        return
    if old_name:
        print(
            f"  ✓ Personality reset to none (was '{old_name}'). Personality "
            "state was previously saved inconsistently across surfaces and "
            "could re-enable a personality you had turned off. "
            f"Run /personality {old_name} to turn it back on.")
    if scrubbed_text:
        print(
            "  ✓ Removed personality text from agent.system_prompt (written "
            "by an older /personality). That field is now reserved for "
            "manual system prompts; personalities live in display.personality.")


def _migrate_to_38(results: Dict[str, Any], quiet: bool) -> None:
    from arkos_cli.relay_plugin_cutover import legacy_relay_plugin_keys

    config = read_raw_config()
    plugins = config.get("plugins")
    if not isinstance(plugins, dict):
        return
    enabled = plugins.get("enabled")
    removed = legacy_relay_plugin_keys(enabled)
    if not removed or not isinstance(enabled, list):
        return

    plugins["enabled"] = [value for value in enabled if value not in removed]
    config["plugins"] = plugins
    _persist_migration(config)
    message = (
        "Removed legacy Relay plugin from plugins.enabled: "
        f"{', '.join(removed)}. Configure native Relay plugins with "
        "ARKOS_NEMO_RELAY_PLUGINS_TOML.")
    results["warnings"].append(message)
    if not quiet:
        print(f"  ⚠ {message}")


def _migrate_to_39(results: Dict[str, Any], quiet: bool) -> None:
    config = read_raw_config()
    changed = False
    for section in ("platform_toolsets", "known_builtin_toolsets"):
        mapping = config.get(section)
        if not isinstance(mapping, dict):
            continue
        for platform, toolsets in mapping.items():
            if isinstance(toolsets, list) and "bfl" in toolsets:
                mapping[platform] = [ts for ts in toolsets if ts != "bfl"]
                changed = True
        if changed:
            config[section] = mapping
    if changed:
        _commit(
            config, results, quiet,
            "removed retired 'bfl' toolset from saved toolset lists",
            "  ✓ Removed the retired BFL FLUX 3 toolset from saved toolset "
            "lists — video generation now lives under `arkos tools` → "
            "Video Generation (Portal Subscription or FAL).")


def _migrate_to_41(results: Dict[str, Any], quiet: bool) -> None:
    from arkos_constants import get_arkos_home
    from tools.bot_mode_probe import _PROTOCOL_HEADING, _arkos_root, _roster, strip_legacy_protocol

    cleaned: List[str] = []
    for name, profile_dir in _roster(_arkos_root(get_arkos_home())):
        soul = profile_dir / "SOUL.md"
        try:
            text = soul.read_text(encoding="utf-8") if soul.is_file() else ""
            if _PROTOCOL_HEADING in text:
                soul.write_text(strip_legacy_protocol(text), encoding="utf-8")
                cleaned.append(name)
        except OSError:
            continue
    if cleaned:
        results["config_added"].append(f"removed legacy Bot Mode section from SOUL.md ({', '.join(cleaned)})")
        if not quiet:
            print(f"  ✓ Removed the plugin-era 'Messaging other agents' section from SOUL.md "
                  f"({', '.join(cleaned)}) — Bot Chat sessions now get the live roster instead.")


MIGRATIONS: Tuple[Tuple[int, Callable[[Dict[str, Any], bool], None]], ...] = (
    (12, _migrate_to_12),
    (13, _migrate_to_13),
    (14, _migrate_to_14),
    (16, _migrate_to_16),
    (17, _migrate_to_17),
    (21, _migrate_to_21),
    (23, _migrate_to_23),
    (25, _rewrite_stale_default(
        section="model_catalog", key="ttl_hours", old=24, new=1,
        added="model_catalog.ttl_hours 24→1",
        message="  ✓ Lowered model_catalog.ttl_hours to 1 (hourly picker refresh)")),
    (29, _migrate_to_29),
    (31, functools.partial(
        _rewrite_key, section="agent", key="verify_on_stop", new=False, create_section=True,
        match=lambda cur: cur is None or _lower_is("auto")(cur),
        added="agent.verify_on_stop=false",
        message=(
            "  ✓ Turned off verify-on-stop (agent.verify_on_stop: false). "
            "Set it to true to re-enable, or \"auto\" for the legacy "
            "surface-aware behavior."))),
    (32, _rewrite_stale_default(
        section="agent", key="verify_on_stop", old=True, new=False,
        added="agent.verify_on_stop=false",
        message=(
            "  ✓ Turned off verify-on-stop (agent.verify_on_stop: false) — "
            "the old default was written into your config as a literal "
            "true. Set it to true again to re-enable, or \"auto\" for the "
            "legacy surface-aware behavior."),
        extra_guard=lambda raw: raw.get("verify_on_stop") is True)),
    (33, _migrate_to_33),
    (34, _migrate_to_34),
    (35, functools.partial(
        _rewrite_key, section="display", key="background_process_notifications",
        match=_lower_is("all"), new="concise",
        added="display.background_process_notifications=concise (was: all)",
        message=(
            "  ✓ Background process notifications switched from 'all' to "
            "'concise' — completions now show a one-line status message "
            "instead of the raw output dump. Set "
            "display.background_process_notifications: all to restore "
            "the old behavior."))),
    (36, _rewrite_stale_default(
        section="delegation", key="max_iterations", old=50, new=250,
        added="delegation.max_iterations=250 (was: 50)",
        message=(
            "  ✓ Raised delegation.max_iterations from 50 to 250 — subagents "
            "now get a larger per-child tool-call budget so delegated work "
            "finishes instead of truncating. Set delegation.max_iterations "
            "back to 50 to restore the old cap."))),
    (37, _rewrite_stale_default(
        section="delegation", key="max_concurrent_children", old=3, new=10,
        added="delegation.max_concurrent_children=10 (was: 3)",
        message=(
            "  ✓ Raised delegation.max_concurrent_children from 3 to 10 — "
            "independent delegated children now fan out wider in parallel. "
            "Each child consumes API tokens independently; set "
            "delegation.max_concurrent_children back to 3 to restore the old cap."))),
    (38, _migrate_to_38),
    (39, _migrate_to_39),
    (40, _rewrite_stale_default(
        section="model_catalog", key="ttl_hours", old=1, new=None,
        added="model_catalog.ttl_hours 1 → ttl_minutes 20 (default)",
        message="  ✓ Model catalog now refreshes every 20 minutes (model_catalog.ttl_minutes)",
        extra_guard=lambda raw: "ttl_minutes" not in raw)),
    (41, _migrate_to_41),
)


def run_migrations(current_ver: int, results: Dict[str, Any], quiet: bool) -> None:
    """Apply every registered migration whose target version exceeds *current_ver*.

    *current_ver* is the on-disk schema version captured ONCE before any step runs and does not
    advance between steps — each step is gated on the same initial value.
    """
    for target_ver, migration_fn in MIGRATIONS:
        if current_ver < target_ver:
            migration_fn(results, quiet)
