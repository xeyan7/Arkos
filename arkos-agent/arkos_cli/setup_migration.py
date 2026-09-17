"""Post-migration section-skip logic and the upstream first-run migration flow (setup.py
re-exports the names it still uses; setup helpers are imported lazily so test patches apply)."""

import importlib.util
import logging
import sys
from functools import partial
from pathlib import Path
from typing import Optional

from arkos_constants import get_optional_skills_dir

logger = logging.getLogger("arkos_cli.setup")

PROJECT_ROOT = Path(__file__).parent.parent.resolve()



_OPENROUTER_ENV_VARS = ("OPENROUTER_API_KEY", "OPENAI_API_KEY")


def _model_section_has_credentials(config: dict) -> bool:
    """True when any known inference provider has usable credentials: ``active_provider`` in the
    auth store (OAuth providers), ``PROVIDER_REGISTRY`` ``api_key_env_vars``, or the legacy
    OpenRouter aggregator env vars (``OPENAI_API_KEY`` / ``OPENROUTER_API_KEY``)."""
    from arkos_cli.setup import get_env_value
    try:
        from arkos_cli.auth import get_active_provider
        if get_active_provider():
            return True
    except Exception:
        pass
    try:
        from arkos_cli.auth import PROVIDER_REGISTRY
    except Exception:
        PROVIDER_REGISTRY = {}  # type: ignore[assignment]

    def _has_key(pconfig) -> bool:
        return any(get_env_value(v) for v in pconfig.api_key_env_vars if v != "CLAUDE_CODE_OAUTH_TOKEN")

    any_openrouter_key = any(get_env_value(v) for v in _OPENROUTER_ENV_VARS)

    model_cfg = config.get("model") if isinstance(config, dict) else None
    if isinstance(model_cfg, dict):
        provider_id = (model_cfg.get("provider") or "").strip().lower()
        if provider_id in PROVIDER_REGISTRY and _has_key(PROVIDER_REGISTRY[provider_id]):
            return True
        if provider_id == "openrouter" and any_openrouter_key:
            return True

    if any_openrouter_key:
        return True
    return any(_has_key(pconfig) for pid, pconfig in PROVIDER_REGISTRY.items() if pid != "copilot")


def _model_summary(config: dict) -> Optional[str]:
    if not _model_section_has_credentials(config):
        return None
    model = config.get("model")
    if isinstance(model, str) and model.strip():
        return model.strip()
    if isinstance(model, dict):
        return str(model.get("default") or model.get("model") or "configured")
    return "configured"


def _cfg_summary(config: dict, section: str, key: str, default, prefix: str) -> str:
    from arkos_cli.setup import cfg_get
    return f"{prefix}{cfg_get(config, section, key, default=default)}"


def _gateway_summary(config: dict) -> Optional[str]:
    from arkos_cli.gateway import _all_platforms, _platform_status
    configured = [
        plat["label"].split("(", 1)[0].strip() or plat["label"]
        for plat in _all_platforms()
        if _platform_status(plat) and _platform_status(plat) != "not configured"
    ]
    return ", ".join(configured) if configured else None


_TOOL_ENV_LABELS = (
    ("ELEVENLABS_API_KEY", "TTS/ElevenLabs"),
    ("BROWSERBASE_API_KEY", "Browser"),
    ("FIRECRAWL_API_KEY", "Firecrawl"),
)


def _tools_summary(config: dict) -> Optional[str]:
    from arkos_cli.setup import get_env_value
    tools = [label for env_var, label in _TOOL_ENV_LABELS if get_env_value(env_var)]
    return ", ".join(tools) if tools else None


_SECTION_SUMMARIES = {
    "model": _model_summary,
    "terminal": partial(_cfg_summary, section="terminal", key="backend", default="local", prefix="backend: "),
    "agent": partial(_cfg_summary, section="agent", key="max_turns", default=90, prefix="max turns: "),
    "gateway": _gateway_summary,
    "tools": _tools_summary,
}


def _get_section_config_summary(config: dict, section_key: str) -> Optional[str]:
    """Short summary if a setup section is already configured (post-upstream-migration skip
    detection), else None. ``get_env_value`` is reached through arkos_cli.setup so test patches
    on ``setup_mod.get_env_value`` apply."""
    summarize = _SECTION_SUMMARIES.get(section_key)
    return summarize(config) if summarize else None


def _skip_configured_section(config: dict, section_key: str, label: str) -> bool:
    """Show an already-configured section summary and offer to skip; True when the user skips."""
    from arkos_cli.setup import print_success, prompt_yes_no
    summary = _get_section_config_summary(config, section_key)
    if not summary:
        return False
    print()
    print_success(f"  {label}: {summary}")
    return not prompt_yes_no(f"  Reconfigure {label.lower()}?", default=False)



_upstream_SCRIPT = (
    get_optional_skills_dir(PROJECT_ROOT / "optional-skills")
    / "migration" / "upstream-migration" / "scripts" / "upstream_to_arkos.py"
)


def _load_upstream_migration_module():
    """Load the upstream_to_arkos migration script as a module; None if it can't be loaded."""
    if not _upstream_SCRIPT.exists():
        return None
    spec = importlib.util.spec_from_file_location("upstream_to_arkos", _upstream_SCRIPT)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return mod


_HIGH_IMPACT_KIND_KEYWORDS = {
    "gateway": "⚠ Gateway/messaging — this will configure Arkos to use your upstream messaging channels",
    "telegram": "⚠ Telegram — this will point Arkos at your upstream Telegram bot",
    "slack": "⚠ Slack — this will point Arkos at your upstream Slack workspace",
    "discord": "⚠ Discord — this will point Arkos at your upstream Discord bot",
    "whatsapp": "⚠ WhatsApp — this will point Arkos at your upstream WhatsApp connection",
    "config": "⚠ Config values — upstream settings may not map 1:1 to Arkos equivalents",
    "soul": "⚠ Instruction file — may contain upstream-specific setup/restart procedures",
    "memory": "⚠ Memory/context file — may reference upstream-specific infrastructure",
    "context": "⚠ Context file — may contain upstream-specific instructions",
}

_MIGRATION_WARNING_NOTES = (
    "  Note: upstream config values may have different semantics in Arkos.",
    "  For example, standard tool_call_execution: \"auto\" ≠ Arkos's yolo mode.",
    "  Instruction files (.md) from upstream may contain incompatible procedures.",
)


def _migrated_row(item: dict, kind: str) -> str:
    dest = item.get("destination", "")
    if dest:
        return f"      {kind:<22s} → {str(dest).replace(str(Path.home()), '~')}"
    return f"      {kind}"


def _reason_row(default_reason: str, item: dict, kind: str) -> str:
    return f"      {kind:<22s}  {item.get('reason', default_reason)}"


def _print_migration_preview(report: dict):
    """Dry-run preview grouped by status, with warnings for high-impact items (gateway takeover,
    config semantics)."""
    from arkos_cli.setup import color, Colors, print_info
    items = report.get("items", [])
    if not items:
        print_info("Nothing to migrate.")
        return
    groups = (
        ("migrated", "  Would import:", Colors.GREEN, _migrated_row),
        ("conflict", "  Would overwrite (conflicts with existing Arkos config):", Colors.YELLOW,
         partial(_reason_row, "already exists")),
        ("skipped", "  Would skip:", Colors.DIM, partial(_reason_row, "")),
    )
    warnings_shown = set()
    for status, header, col, row in groups:
        group = [i for i in items if i.get("status") == status]
        if not group:
            continue
        print(color(header, col))
        for item in group:
            kind = item.get("kind", "unknown")
            print(row(item, kind))
            if status == "migrated":
                kind_lower, dest_lower = kind.lower(), str(item.get("destination", "")).lower()
                warnings_shown.update(
                    w for kw, w in _HIGH_IMPACT_KIND_KEYWORDS.items() if kw in kind_lower or kw in dest_lower)
        print()
    if warnings_shown:
        print(color("  ── Warnings ──", Colors.YELLOW))
        for warning in sorted(warnings_shown):
            print(color(f"    {warning}", Colors.YELLOW))
        print()
        for line in _MIGRATION_WARNING_NOTES:
            print(color(line, Colors.YELLOW))
        print()


def _run_migrator(mod, upstream_dir: Path, arkos_home: Path, selected, *, execute: bool, overwrite: bool):
    """Run a Migrator with the fixed first-time-setup options and return its report."""
    return mod.Migrator(
        source_root=upstream_dir.resolve(), target_root=arkos_home.resolve(), execute=execute,
        workspace_target=None, overwrite=overwrite, migrate_secrets=True, output_dir=None,
        selected_options=selected, preset_name="full",
    ).migrate()


_FAILED = object()


def _migration_step(label: str, log_label: str, fn):
    """Run one migration phase; on failure warn ``"<label>: <exc>"``, log the trace and return
    ``_FAILED`` (the caller aborts)."""
    from arkos_cli.setup import print_warning
    try:
        return fn()
    except Exception as e:
        print_warning(f"{label}: {e}")
        logger.debug(log_label, exc_info=True)
        return _FAILED


def _offer_upstream_migration(arkos_home: Path) -> bool:
    return False
