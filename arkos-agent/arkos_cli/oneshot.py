"""Oneshot (-z) mode: send a prompt, get the final content block, exit.

Toolsets = explicit --toolsets, else the user's "cli" toolsets from `arkos tools`. Rules /
memory / AGENTS.md / preloaded skills = same as a normal chat turn. Approvals are auto-bypassed
(ARKOS_YOLO_MODE=1). Model/provider mirror `arkos chat`: both optional; only --model → auto-detect
the provider; only --provider → error (ambiguous).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from gateway.session_context import declare_stateless_channel
from arkos_cli.fallback_config import get_fallback_chain

_ALL_TOOLSETS = {"all", "*"}

_USAGE_KEYS = (
    "estimated_cost_usd", "cost_status", "cost_source", "input_tokens", "output_tokens",
    "cache_read_tokens", "cache_write_tokens", "reasoning_tokens", "total_tokens", "api_calls",
    "model", "provider", "session_id", "completed",
)


def _normalize_toolsets(toolsets: object = None) -> list[str] | None:
    """Split repeated/comma-separated toolset flags into a clean list (``None`` when empty)."""
    if not toolsets:
        return None
    items = toolsets if isinstance(toolsets, (list, tuple)) else [toolsets]
    parts = [str(item).split(",") if isinstance(item, str) else [str(item)] for item in items]
    return [p.strip() for chunk in parts for p in chunk if p.strip()] or None


def _normalize_skills(skills: object = None) -> list[str]:
    """Normalize repeated/comma-separated skill flags and preserve order."""
    return list(dict.fromkeys(_normalize_toolsets(skills) or []))


def _build_preloaded_skills_prompt(skills: object = None) -> str | None:
    """Load requested skills using the same partial-success contract as CLI chat."""
    parsed_skills = _normalize_skills(skills)
    if not parsed_skills:
        return None

    from agent.skill_commands import build_preloaded_skills_prompt

    skills_prompt, loaded_skills, missing_skills = build_preloaded_skills_prompt(parsed_skills)
    if missing_skills:
        missing_display = ", ".join(missing_skills)
        if not loaded_skills:
            raise ValueError(f"Unknown skill(s): {missing_display}")
        logging.warning(
            "Unknown skill(s) requested, skipping: %s. Continuing with: %s. "
            "List available skills with `arkos skills list`.",
            missing_display,
            ", ".join(loaded_skills),
        )
    return skills_prompt or None


def _configured_mcp_servers() -> tuple[set[str], set[str]]:
    """``(enabled, disabled)`` MCP server names from config; both empty on any error."""
    try:
        from arkos_cli.config import read_raw_config
        from arkos_cli.tools_config import _parse_enabled_flag

        cfg = read_raw_config()
        mcp_servers = cfg.get("mcp_servers") if isinstance(cfg.get("mcp_servers"), dict) else {}
        enabled: set[str] = set()
        disabled: set[str] = set()
        for name, server_cfg in mcp_servers.items():
            if not isinstance(server_cfg, dict):
                continue
            target = enabled if _parse_enabled_flag(server_cfg.get("enabled", True), default=True) else disabled
            target.add(str(name))
        return enabled, disabled
    except Exception:
        return set(), set()


def _validate_explicit_toolsets(toolsets: object = None) -> tuple[list[str] | None, str | None]:
    normalized = _normalize_toolsets(toolsets)
    if normalized is None:
        return None, None

    try:
        from toolsets import validate_toolset
    except Exception as exc:
        return None, f"arkos -z: failed to validate --toolsets: {exc}\n"

    built_in = [name for name in normalized if validate_toolset(name)]
    unresolved = [name for name in normalized if name not in built_in]

    if unresolved:
        try:
            from arkos_cli.plugins import discover_plugins

            discover_plugins()
            plugin_valid = [name for name in unresolved if validate_toolset(name)]
        except Exception:
            plugin_valid = []
        built_in.extend(plugin_valid)
        unresolved = [name for name in unresolved if name not in plugin_valid]

    if any(name in _ALL_TOOLSETS for name in built_in):
        ignored = [name for name in normalized if name not in _ALL_TOOLSETS]
        if ignored:
            sys.stderr.write(
                "arkos -z: --toolsets all enables every toolset; "
                f"ignoring additional entries: {', '.join(ignored)}\n"
            )
        return None, None

    mcp_names, mcp_disabled = _configured_mcp_servers() if unresolved else (set(), set())
    mcp_valid = [name for name in unresolved if name in mcp_names]
    disabled = [name for name in unresolved if name in mcp_disabled]
    unknown = [name for name in unresolved if name not in mcp_names and name not in mcp_disabled]
    valid = built_in + mcp_valid

    if unknown:
        sys.stderr.write(f"arkos -z: ignoring unknown --toolsets entries: {', '.join(unknown)}\n")
    if disabled:
        sys.stderr.write(
            "arkos -z: ignoring disabled MCP servers (set enabled: true in config.yaml to use): "
            f"{', '.join(disabled)}\n"
        )
    if not valid:
        return None, "arkos -z: --toolsets did not contain any valid toolsets.\n"
    return valid, None


def _write_usage_file(path: Optional[str], result: dict, failure: Optional[str] = None) -> None:
    """Best-effort JSON usage report for pipelines (``-z --usage-file``).

    Written even on failure so callers can always account for spend. Never raises — a broken usage
    write must not mask the run's own outcome.
    """
    if not path:
        return
    try:
        report = {key: result.get(key) for key in _USAGE_KEYS}
        report["failed"] = bool(result.get("failed")) or failure is not None
        report["service_tier"] = result.get("service_tier")
        if failure is not None:
            report["failure"] = failure
        out = Path(path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def run_oneshot(
    prompt: str,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    toolsets: object = None,
    skills: object = None,
    usage_file: Optional[str] = None,
) -> int:
    """Execute a single prompt and print only the final content block.

    Model/provider fall back to ``ARKOS_INFERENCE_MODEL`` and config.yaml. ``usage_file`` gets a
    JSON usage report even when the run fails. Returns the exit code; the caller owns process
    termination.
    """
    logging.disable(logging.CRITICAL)

    env_model_early = os.getenv("ARKOS_INFERENCE_MODEL", "").strip()
    if provider and not ((model or "").strip() or env_model_early):
        sys.stderr.write(
            "arkos -z: --provider requires --model (or ARKOS_INFERENCE_MODEL). "
            "Pass both explicitly, or neither to use your configured defaults.\n"
        )
        return 2

    explicit_toolsets, toolsets_error = _validate_explicit_toolsets(toolsets)
    if toolsets_error:
        sys.stderr.write(toolsets_error)
        return 2
    use_config_toolsets = _normalize_toolsets(toolsets) is None

    os.environ["ARKOS_YOLO_MODE"] = "1"
    os.environ["ARKOS_ACCEPT_HOOKS"] = "1"

    declare_stateless_channel()

    real_stdout = sys.stdout
    real_stderr = sys.stderr

    response: Optional[str] = None
    result: dict = {}
    failure: BaseException | None = None
    with open(os.devnull, "w", encoding="utf-8") as devnull, redirect_stdout(devnull), redirect_stderr(devnull):
        try:
            response, result = _run_agent(
                prompt,
                model=model,
                provider=provider,
                toolsets=explicit_toolsets,
                use_config_toolsets=use_config_toolsets,
                skills=skills,
            )
        except BaseException as exc:  # noqa: BLE001
            failure = exc

    if failure is not None:
        if isinstance(failure, (KeyboardInterrupt, SystemExit)):
            _write_usage_file(usage_file, result, failure=repr(failure))
            raise failure
        _write_usage_file(usage_file, result, failure=str(failure))
        real_stderr.write(f"arkos -z: agent failed: {failure}\n")
        real_stderr.flush()
        return 1

    _write_usage_file(usage_file, result)

    if response:
        from agent.message_sanitization import _sanitize_surrogates

        response = _sanitize_surrogates(response)
        real_stdout.write(response)
        if not response.endswith("\n"):
            real_stdout.write("\n")
        real_stdout.flush()

    if not (response or "").strip():
        if result.get("failed") or result.get("partial"):
            return 2
        real_stderr.write("arkos -z: no final response was produced; treating the run as failed.\n")
        real_stderr.flush()
        return 1
    return 0


def _create_session_db_for_oneshot():
    """Best-effort SessionDB — oneshot bypasses ``ArkosCLI._init_agent()``, so it must wire the
    SQLite store itself or ``session_search`` is advertised but always unavailable."""
    try:
        from arkos_state import SessionDB

        return SessionDB()
    except Exception as exc:
        logging.debug("SQLite session store not available for oneshot mode: %s", exc)
        return None


@dataclass
class _ModelChoice:
    model: str
    provider: str | None
    base_url: str | None = None
    api_key: str | None = None


def _configured_model(model_cfg: object) -> str:
    if isinstance(model_cfg, str):
        return model_cfg
    raw = model_cfg.get("default") or model_cfg.get("model") or ""
    if isinstance(raw, dict):
        from arkos_cli.config import split_model_config_default

        return split_model_config_default(raw)[0]
    return str(raw or "")


def _resolve_model_and_provider(cfg: dict, model: Optional[str], provider: Optional[str]) -> _ModelChoice:
    """Effective model = arg → env → config; provider = arg → auto-detect → config/env.

    Auto-detection only runs when the model was explicitly requested (arg or env var) — same
    semantic as ``/model <name>`` — because the configured default provider may not host it.
    Config-sourced models are the "use my defaults" path and keep the configured provider.
    """
    from arkos_cli.models import detect_provider_for_model

    model_cfg = cfg.get("model") or {}
    env_model = os.getenv("ARKOS_INFERENCE_MODEL", "").strip()
    explicit_model = (model or "").strip() or env_model
    choice = _ModelChoice(explicit_model or _configured_model(model_cfg), (provider or "").strip() or None)
    if choice.provider is not None or not explicit_model:
        return choice

    try:
        from arkos_cli import model_switch as _ms
        _ms._ensure_direct_aliases()
        direct = _ms.DIRECT_ALIASES.get(explicit_model.strip().lower())
    except Exception:
        direct = None
    if direct is None:
        cfg_provider = ""
        if isinstance(model_cfg, dict):
            cfg_provider = str(model_cfg.get("provider") or "").strip().lower()
        current_provider = cfg_provider or os.getenv("ARKOS_INFERENCE_PROVIDER", "").strip().lower() or "auto"
        detected = detect_provider_for_model(explicit_model, current_provider)
        if detected:
            choice.provider, choice.model = detected
        return choice

    choice.model = direct.model
    choice.provider = direct.provider
    try:
        choice.provider, choice.api_key = _ms.direct_alias_runtime_request(direct)
    except Exception:
        choice.api_key = None
    if direct.base_url:
        choice.base_url = direct.base_url.rstrip("/")
    return choice


def _run_agent(
    prompt: str,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    toolsets: object = None,
    use_config_toolsets: bool = True,
    skills: object = None,
) -> tuple[str, dict]:
    """Build an AIAgent exactly like a normal CLI chat turn, run one conversation, and return
    ``(final_response, run_result)``. Imports are local to keep CLI startup cheap."""
    from arkos_cli.config import load_config
    from arkos_cli.runtime_provider import resolve_runtime_provider
    from arkos_cli.tools_config import _get_platform_tools
    from run_agent import AIAgent

    cfg = load_config()
    choice = _resolve_model_and_provider(cfg, model, provider)
    runtime = resolve_runtime_provider(
        requested=choice.provider,
        target_model=choice.model or None,
        explicit_base_url=choice.base_url,
        explicit_api_key=choice.api_key,
    )

    toolsets_list = _normalize_toolsets(toolsets)
    if toolsets_list is None and use_config_toolsets:
        toolsets_list = sorted(_get_platform_tools(cfg, "cli"))

    from arkos_cli.mcp_startup import ensure_mcp_discovery_before_agent_build

    ensure_mcp_discovery_before_agent_build(logger=logging.getLogger(__name__), single_query=True)

    skills_prompt = _build_preloaded_skills_prompt(skills)

    session_db = _create_session_db_for_oneshot()
    agent = None
    try:
        agent = AIAgent(
            api_key=runtime.get("api_key"),
            base_url=runtime.get("base_url"),
            provider=runtime.get("provider"),
            requested_provider=runtime.get("requested_provider"),
            api_mode=runtime.get("api_mode"),
            model=choice.model,
            enabled_toolsets=toolsets_list,
            quiet_mode=True,
            platform="cli",
            session_db=session_db,
            credential_pool=runtime.get("credential_pool"),
            fallback_model=get_fallback_chain(cfg) or None,
            ephemeral_system_prompt=skills_prompt,
            clarify_callback=_oneshot_clarify_callback,
        )
        agent.suppress_status_output = True
        agent.stream_delta_callback = None
        agent.tool_gen_callback = None

        result = agent.run_conversation(prompt)
        return (result.get("final_response") or "", result)
    finally:
        _close_agent(agent, session_db)


def _quietly(what: str, fn) -> None:
    """Run a cleanup step, logging (never raising) on failure."""
    try:
        fn()
    except Exception:
        logging.debug("oneshot %s failed", what, exc_info=True)


def _linger_for_background_completions() -> None:
    from tools.process_registry import process_registry

    process_registry.wait_for_pending_completions(None)


def _close_agent(agent, session_db) -> None:
    """Teardown mirroring gateway/run.py:_cleanup_agent_resources (NOT cli.py:_run_cleanup):
    oneshot has no _active_agent_ref and the hard-exit path skips finalizers."""
    if agent is not None:
        _quietly("background completion wait", _linger_for_background_completions)
        session_messages = getattr(agent, "_session_messages", None)
        memory_args = (session_messages,) if isinstance(session_messages, list) else ()
        _quietly("memory/context cleanup", lambda: agent.shutdown_memory_provider(*memory_args))
        _quietly("agent cleanup", lambda: agent.close())
    if session_db is not None:
        _quietly("session store cleanup", lambda: session_db.close())


def _oneshot_clarify_callback(question: str, choices=None, multi_select=False) -> str:
    """Clarify is disabled in oneshot mode — tell the agent to pick a default and proceed."""
    if choices:
        what = "subset" if multi_select else "option"
        return (
            f"[oneshot mode: no user available. Pick the best {what} from "
            f"{choices} using your own judgment and continue.]"
        )
    return "[oneshot mode: no user available. Make the most reasonable assumption you can and continue.]"
