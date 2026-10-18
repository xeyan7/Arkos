"""Cron job management tool: one compressed action-oriented `cronjob_manage` tool
(schema/context bloat avoided); `cronjob()` stays callable for direct Python callers."""

import contextlib
import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from arkos_constants import display_arkos_home

logger = logging.getLogger(__name__)

_CRON_RUN_HEARTBEAT_INTERVAL = 10.0
_CRON_RUN_HEARTBEAT_CEILING = 6 * 3600.0

sys.path.insert(0, str(Path(__file__).parent.parent))

from cron.jobs import (
    AmbiguousJobReference,
    claim_job_for_fire,
    get_job,
    is_job_runnable,
    list_jobs,
    mark_job_run,
    parse_schedule,
    pause_job,
    remove_job,
    resolve_job_ref,
    resume_job,
    update_job)
from tools.cronjob_prompt_scan import _scan_cron_prompt
from tools.cronjob_job_args import (
    _apply_continuity,
    _canonical_skills,
    _clean_str_list,
    _format_job,
    _gateway_liveness_notice,
    _local_delivery_notice,
    _mode_guidance_notes,
    _normalize_deliver_param,
    _normalize_optional_job_value,
    _origin_from_env,
    _repeat_display,
    _resolve_cron_context_deliver,
    _split_monitor_arg,
    _validate_bot_chat_deliver,
    _validate_context_from_refs,
    _validate_cron_base_url,
    _validate_cron_script_path)
from tools.registry import registry, tool_error


def _dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, indent=2)


def _notify_provider_jobs_changed_safe() -> None:
    """Tell the active scheduler provider the job set changed; best-effort, never raises."""
    try:
        from cron.scheduler import _notify_provider_jobs_changed
        _notify_provider_jobs_changed()
    except Exception:
        pass



def _relay_fronted_delivery_platforms(job: Dict[str, Any]) -> set:
    """Delivery-platform names for this job that the relay connector fronts."""
    try:
        from gateway.relay import relay_fronted_platforms
    except Exception:
        return set()
    fronted = relay_fronted_platforms()
    if not fronted:
        return set()
    try:
        from cron.scheduler import _resolve_delivery_targets
        targets = _resolve_delivery_targets(job) or []
    except Exception:
        return set()
    return {t.get("platform") for t in targets if t.get("platform")} & fronted


def _api_server_base_url() -> str:
    """``http://host:port`` of the local api_server, mirroring its bind resolution
    (extra.host -> API_SERVER_HOST -> 127.0.0.1); a wildcard bind listens on loopback too."""
    import os
    port_raw = os.getenv("API_SERVER_PORT", "").strip()
    try:
        port = int(port_raw) if port_raw else 8642
    except ValueError:
        port = 8642
    try:
        from arkos_cli.config import cfg_get, load_config_readonly
        host = str(cfg_get(load_config_readonly(), "platforms", "api_server", "extra", "host", default="") or "").strip()
    except Exception:
        host = ""
    host = host or os.getenv("API_SERVER_HOST", "").strip()
    if not host or host in ("0.0.0.0", "::", "*"):
        host = "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{port}"


def _forward_relay_fronted_run(job: Dict[str, Any], extra_prompt: Optional[str] = None) -> Optional[str]:
    """Forward a manual run to the gateway when it targets a relay-fronted platform: such delivery
    has no standalone sender — the gateway's live relay adapter is the only path, reached via
    ``POST /api/jobs/{id}/run`` (marks the job due; ``extra_prompt`` rides in the body). Returns a
    JSON result string when forwarding engages, else None (normal in-process run)."""
    if not _relay_fronted_delivery_platforms(job):
        return None
    from agent.secret_scope import get_secret
    key = get_secret("API_SERVER_KEY", "") or ""
    try:
        import httpx
        resp = httpx.post(
            f"{_api_server_base_url()}/api/jobs/{job['id']}/run", headers={"Authorization": f"Bearer {key}"},
            json=({"prompt": extra_prompt} if extra_prompt else {}), timeout=10.0)
    except Exception:
        resp = None
    if resp is not None and resp.status_code < 300:
        return _dumps({
            "success": True,
            "forwarded_to_gateway": True,
            "note": (
                "This job targets a relay-fronted platform; it was dispatched "
                "to the running gateway, whose live relay adapter owns that "
                "delivery."),
        })
    return _dumps({
        "success": False,
        "error": (
            "This job targets a relay-fronted platform, which has no "
            "standalone sender. Start the gateway — its ticker will "
            "deliver the job on schedule via the live relay adapter."),
    })


def _manual_run_delivery_note(deliver: str, refreshed: Dict[str, Any]) -> str:
    """Parenthetical delivery note for a manual run's summary; follows the refreshed record's
    ``last_delivery_error`` so the summary never claims success over a failed delivery.

    Follows the refreshed job record: ``run_one_job`` writes ``last_delivery_error`` via
    ``mark_job_run`` when the post-run delivery (telegram/discord/…) failed, and the summary must not claim
    success over that record — the calling agent relays this line to the user. Local jobs never deliver; an
    empty/missing error keeps the legacy wording byte-for-byte.
    """
    if not deliver or deliver == "local":
        return " (output saved locally only)"
    err = str(refreshed.get("last_delivery_error") or "").strip()
    if not err:
        if refreshed.get("last_delivery_queued"):
            return " (output queued for Bot Chat; completion unverified, do not resend)"
        return " (output was delivered there by the job itself)"
    return f" (⚠ delivery FAILED: {err[:200]})"


_ALREADY_RUNNING_ERROR = (
    "Job is already running (a scheduler tick or another "
    "manual run is executing it); not started again.")


def _claim_for_manual_run(job_id: str, log_label: str):
    """At-most-once claim shared by the sync and background run paths: ``(claimed_job, None)`` or
    ``(None, error_dict)`` in the ``_execute_job_now`` shape. A lost claim is labelled precisely —
    claim_job_for_fire also returns False for paused/disabled/missing jobs, not just in-flight ones."""
    try:
        claimed_job = claim_job_for_fire(job_id, return_job=True)
        if isinstance(claimed_job, dict):
            return claimed_job, None
        refreshed = get_job(job_id)
        if refreshed is None:
            reason = "Job no longer exists; nothing to run."
        elif not is_job_runnable(refreshed):
            reason = "Job is paused/disabled; resume it before running."
        else:
            reason = "Job is already being fired by the scheduler; not run again."
        return None, {"claimed": False, "success": False, "error": reason}
    except Exception as e:
        logger.error("Failed to claim cron job %s for %s: %s", job_id, log_label, e)
        with contextlib.suppress(Exception):
            mark_job_run(job_id, False, str(e))
        return None, {"claimed": True, "success": False, "error": str(e)}


def _execute_job_now(job: Dict[str, Any], extra_prompt: Optional[str] = None) -> Dict[str, Any]:
    """Run a job now, outside the scheduler tick: claim via ``claim_job_for_fire`` (the ticker's
    CAS, so a concurrent tick cannot double-fire and next_run_at advances), then fire through
    the shared ``run_one_job`` body. Returns {"claimed", "success", "error"}."""
    claimed_job, err = _claim_for_manual_run(job["id"], "immediate run")
    return err if err is not None else _run_claimed_job(claimed_job, extra_prompt=extra_prompt)


@contextlib.contextmanager
def _run_heartbeat(job_name: str):
    """Heartbeat into the caller's activity tracker while a manual run executes (minutes,
    synchronously on the caller's thread — without tool activity the gateway inactivity
    watchdog would kill the parent turn). Best-effort: no callback -> no thread."""
    stop = threading.Event()
    thread = None
    try:
        from tools.environments.base import get_activity_callback
        activity_cb = get_activity_callback()
    except Exception:
        activity_cb = None

    def _heartbeat_loop() -> None:
        started = time.monotonic()
        while not stop.wait(_CRON_RUN_HEARTBEAT_INTERVAL):
            elapsed = time.monotonic() - started
            if elapsed > _CRON_RUN_HEARTBEAT_CEILING:
                logger.warning(
                    "cronjob run heartbeat ceiling reached for job "
                    "'%s' (%.0fs) — stopping heartbeat; gateway watchdog regains authority",
                    job_name, elapsed)
                return
            try:
                activity_cb(f"cronjob: running job '{job_name}' ({int(elapsed)}s elapsed)")
            except Exception:
                continue

    if activity_cb is not None:
        thread = threading.Thread(target=_heartbeat_loop, daemon=True, name="cronjob-run-heartbeat")
        thread.start()
    try:
        yield
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=_CRON_RUN_HEARTBEAT_INTERVAL + 1)


def _run_claimed_job(job: Dict[str, Any], extra_prompt: Optional[str] = None) -> Dict[str, Any]:
    """Fire an already-claimed job through the shared ``run_one_job`` body (split from
    ``_execute_job_now`` so the background path can claim synchronously and hand the run
    to a worker). Returns {"claimed": True, "success": bool, "error": ...}."""
    job_id = job["id"]
    _registered = False
    fire_owner = None
    try:
        from cron.scheduler import release_running_job, run_one_job, try_register_running_job

        if not try_register_running_job(job_id):
            return {"claimed": True, "success": False, "error": _ALREADY_RUNNING_ERROR}
        _registered = True

        claim = job.get("fire_claim")
        fire_owner = str(claim.get("by") or "") if isinstance(claim, dict) else None

        runner_ref = getattr(sys.modules.get("gateway.run"), "_gateway_runner_ref", None)
        runner = runner_ref() if callable(runner_ref) else None
        adapters = getattr(runner, "adapters", None) if runner is not None else None
        gateway_loop = getattr(runner, "_gateway_loop", None) if runner is not None else None
        try:
            with _run_heartbeat(str(job.get("name") or job_id)):
                processed = run_one_job(job, adapters=adapters, loop=gateway_loop, extra_prompt=extra_prompt)
        finally:
            _registered = False
            release_running_job(job_id)
        refreshed = get_job(job_id) or {}
        execution = None
        execution_id = job.get("execution_id")
        if execution_id:
            from cron.executions import get_execution

            execution = get_execution(str(execution_id))
        last_status = refreshed.get("last_status")
        run_error = refreshed.get("last_error")
        if last_status == "delivery_failed" and not run_error:
            run_error = refreshed.get("last_delivery_error")
        ok = last_status in {"ok", "delivery_queued"}
        if execution is not None and execution.get("status") != "completed":
            ok = False
            run_error = execution.get("error") or f"execution ended in {execution.get('status') or 'unknown'} state"
        return {"claimed": True, "success": bool(processed and ok), "error": run_error}
    except Exception as e:
        logger.error("Failed to execute cron job %s immediately: %s", job_id, e)
        if _registered:
            with contextlib.suppress(Exception):
                release_running_job(job_id)
        with contextlib.suppress(Exception):
            mark_job_run(job_id, False, str(e), expected_fire_owner=fire_owner)
        return {"claimed": True, "success": False, "error": str(e)}


def _latest_job_output_excerpt(job_id: str, max_chars: int = 2000) -> Optional[str]:
    """Excerpt of the job's most recent saved output file for the background completion
    block (parent sees what the job produced). Never raises."""
    try:
        from cron.jobs import get_cron_output_dir
        files = sorted((get_cron_output_dir() / job_id).glob("*.md"))
        text = files[-1].read_text(encoding="utf-8", errors="replace").strip() if files else ""
        if not text:
            return None
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n… (truncated; full output: {files[-1]})"
        return text
    except Exception:
        return None


def _reap_stale_executions(job_name: str) -> None:
    """Reap execution rows left 'claimed'/'running' by a provably-dead owner (e.g. a prior
    one-shot `arkos cron run` that died mid-run). The ticker does this at startup; one-shot
    invocations have no such moment, so a stale claim would block every later manual run.
    Best-effort self-heal: must not block dispatch."""
    try:
        from cron.executions import recover_interrupted_executions
        _reclaimed = recover_interrupted_executions()
        if _reclaimed:
            logger.warning(
                "Reclaimed %d stale cron execution(s) from dead owner(s) before dispatching job '%s'",
                _reclaimed, job_name)
    except Exception as _reap_exc:
        logger.debug("Stale execution reclaim failed: %s", _reap_exc)


def _background_session_key(session_id: Optional[str]) -> str:
    """Routing key for a detached completion, captured on THIS thread (contextvars don't
    cross the pool). Empty string = no durable consumer."""
    try:
        from tools.approval_context import get_current_session_key
        session_key = get_current_session_key(default="")
    except Exception:
        session_key = ""
    return session_key or (str(session_id) if session_id else "")


def _manual_run_completion(
    res: Dict[str, Any], job_id: str, job_name: str, deliver: str, started_at: float) -> Dict[str, Any]:
    """Async-delegation completion block for a finished background manual run."""
    duration = round(time.time() - started_at, 2)
    refreshed = get_job(job_id) or {}
    lines = [
        f"Cron job '{job_name}' ({job_id}) finished its manual run.",
        f"Result: {'ok' if res.get('success') else 'FAILED'}"
        + (f" — {res.get('error')}" if res.get("error") else ""),
        f"Delivery target: {deliver}" + _manual_run_delivery_note(deliver, refreshed),
    ]
    if refreshed.get("next_run_at"):
        lines.append(f"Next scheduled run: {refreshed['next_run_at']}")
    excerpt = _latest_job_output_excerpt(job_id)
    if excerpt:
        lines += ["--- JOB OUTPUT ---", excerpt]
    return {
        "status": "completed" if res.get("success") else "error", "summary": "\n".join(lines),
        "error": res.get("error"), "api_calls": 0, "duration_seconds": duration,
    }


def _try_dispatch_background_run(
    job: Dict[str, Any], session_id: Optional[str] = None, extra_prompt: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Claim ``job`` now (SYNCHRONOUSLY, so unrunnable jobs report immediately), then fire it
    on the async-delegation executor like ``delegate_task``'s background mode: the tool returns
    a handle and a ``type="async_delegation"`` completion re-enters as a fresh turn (role
    alternation legal, prompt cache intact) instead of blocking the parent turn for minutes.
    Returns None when background delivery is unavailable (caller runs sync); ``{"claimed":
    False}`` on a lost claim; ``{"claimed": True, "dispatched": True, "delegation_id"}``; or
    ``{"claimed": True, "dispatched": False, ...}`` when the pool was full and it ran inline."""
    try:
        from gateway.session_context import async_delivery_supported
        if not async_delivery_supported():
            return None
    except Exception:
        pass

    job_id = job["id"]
    job_name = str(job.get("name") or job_id)
    _reap_stale_executions(job_name)

    session_key = _background_session_key(session_id)
    if not session_key:
        return None

    try:
        from cron.scheduler import get_running_job_ids
        if job_id in get_running_job_ids():
            return {"claimed": False, "success": False, "error": _ALREADY_RUNNING_ERROR}
    except Exception:
        pass

    claimed_job, err = _claim_for_manual_run(job_id, "background run")
    if err is not None:
        if err["claimed"]:
            err["dispatched"] = False
        return err

    origin_ui_session_id = ""
    try:
        from gateway.session_context import get_session_env
        origin_ui_session_id = get_session_env("ARKOS_UI_SESSION_ID", "") or ""
    except Exception:
        pass

    try:
        from tools.async_delegation import _current_origin_session_id, dispatch_async_delegation
        origin_session_id = _current_origin_session_id()
    except Exception as e:
        logger.warning(
            "cronjob run: async delegation registry unavailable (%s); running job '%s' inline.", e, job_name)
        result = _run_claimed_job(claimed_job, extra_prompt=extra_prompt)
        result["dispatched"] = False
        return result

    try:
        from tools.delegate_tool import _get_max_async_children
        max_async = _get_max_async_children()
    except Exception:
        max_async = 3

    started_at = time.time()
    from cron.scheduler import _normalize_deliver_value
    deliver = _normalize_deliver_value(claimed_job.get("deliver", "local"))

    def _runner() -> Dict[str, Any]:
        res = _run_claimed_job(claimed_job, extra_prompt=extra_prompt)
        return _manual_run_completion(res, job_id, job_name, deliver, started_at)

    dispatch = dispatch_async_delegation(
        goal=f"Manual run of cron job '{job_name}' ({job_id})",
        context=("Triggered via cronjob(action='run'). The job executed in its own "
                 "fresh cron session; this block reports its outcome."),
        toolsets=None, role="cron_run", model=job.get("model"), session_key=session_key,
        parent_session_id=str(session_id) if session_id else None, runner=_runner,
        origin_ui_session_id=origin_ui_session_id, origin_session_id=origin_session_id,
        max_async_children=max_async)
    if dispatch.get("status") == "dispatched":
        return {"claimed": True, "dispatched": True, "delegation_id": dispatch.get("delegation_id")}

    logger.info(
        "cronjob run: background pool unavailable (%s); running job '%s' inline.",
        dispatch.get("error", "rejected"), job_name)
    result = _run_claimed_job(job, extra_prompt=extra_prompt)
    result["dispatched"] = False
    return result



def _with_guidance(result: Dict[str, Any], job: Dict[str, Any], deliver: Optional[str]) -> Dict[str, Any]:
    """Attach mode/delivery guidance (create and update echo the same notes)."""
    _notes = _mode_guidance_notes(job, deliver)
    if _notes:
        result["guidance"] = _notes
    return result


def _action_create(a: Dict[str, Any]) -> str:
    prompt, script = a["prompt"], a["script"]
    deliver = _normalize_deliver_param(a["deliver"])
    if not a["schedule"]:
        return tool_error("schedule is required for create", success=False)
    canonical_skills = _canonical_skills(a["skill"], a["skills"])
    _no_agent = bool(a["no_agent"])
    if _no_agent:
        if not script:
            return tool_error(
                "create with no_agent=True requires a script — "
                "the script is the job. In no_agent mode the LLM is "
                "skipped entirely: prompt and skills are ignored, "
                "non-empty stdout is delivered verbatim, empty stdout "
                "sends nothing (watchdog pattern), and a non-zero exit or timeout sends an error alert.",
                success=False)
    elif not prompt and not canonical_skills:
        return tool_error("create requires either prompt or at least one skill", success=False)
    error = (
        (prompt and _scan_cron_prompt(prompt))
        or (script and _validate_cron_script_path(script))
        or (a["monitor_script"] and _validate_cron_script_path(a["monitor_script"]))
        or _validate_cron_base_url(a["provider"], a["base_url"])
        or _validate_bot_chat_deliver(deliver)
        or _validate_bot_chat_deliver(_normalize_deliver_param(a["failure_deliver"]))
        or (a["context_from"] and _validate_context_from_refs(
            [a["context_from"]] if isinstance(a["context_from"], str) else a["context_from"])))
    if error:
        return tool_error(error, success=False)

    context_from = a["context_from"]
    if a["continuity"] is not None:
        context_from = _apply_continuity(context_from, a["continuity"])

    from cron.scheduler import CronSchedulerRegistrationError, create_job_with_scheduler_registration
    try:
        job = create_job_with_scheduler_registration(
            prompt=prompt or "", schedule=a["schedule"], name=a["name"], repeat=a["repeat"],
            deliver=_resolve_cron_context_deliver(deliver), origin=_origin_from_env(), skills=canonical_skills,
            model=_normalize_optional_job_value(a["model"]), provider=_normalize_optional_job_value(a["provider"]),
            base_url=_normalize_optional_job_value(a["base_url"], strip_trailing_slash=True),
            script=_normalize_optional_job_value(script), context_from=context_from,
            enabled_toolsets=a["enabled_toolsets"] or None, workdir=_normalize_optional_job_value(a["workdir"]),
            no_agent=_no_agent, attach_to_session=a["attach_to_session"],
            monitor_script=_normalize_optional_job_value(a["monitor_script"]),
            monitor_url=_normalize_optional_job_value(a["monitor_url"]),
            reasoning_effort=a["reasoning_effort"],
            failure_deliver=_resolve_cron_context_deliver(_normalize_deliver_param(a["failure_deliver"])),
            **({"paused": a["paused"], "paused_reason": a["paused_reason"]}
               if a["paused"] is not False or a["paused_reason"] is not None else {}))
    except CronSchedulerRegistrationError as exc:
        _partial = exc.to_dict()
        return tool_error(_partial.pop("error"), success=False, **_partial)
    _create_message = " ".join(filter(None, (f"Cron job '{job['name']}' created.",
        "Created PAUSED — resume to schedule, or explicitly run now." if not job.get("enabled", True) else None,
        _local_delivery_notice(job, deliver))))
    _result = {
        "success": True, "job_id": job["id"], "name": job["name"], "skill": job.get("skill"),
        "skills": job.get("skills", []), "schedule": job["schedule_display"], "repeat": _repeat_display(job),
        "deliver": job.get("deliver", "local"), "next_run_at": job["next_run_at"], "job": _format_job(job),
        "message": _create_message, **_gateway_liveness_notice(),
    }
    return _dumps(_with_guidance(_result, job, deliver))


def _action_list(a: Dict[str, Any]) -> str:
    jobs = [_format_job(job) for job in list_jobs(include_disabled=a["include_disabled"])]
    _result = {"success": True, "count": len(jobs), "jobs": jobs}
    if jobs:
        _result.update(_gateway_liveness_notice(plural=True))
    return _dumps(_result)


def _action_remove(job: Dict[str, Any], a: Dict[str, Any]) -> str:
    job_id = job["id"]
    if not remove_job(job_id):
        return tool_error(f"Failed to remove job '{job_id}'", success=False)
    _notify_provider_jobs_changed_safe()
    return _dumps({
        "success": True,
        "message": f"Cron job '{job['name']}' removed.",
        "removed_job": {"id": job_id, "name": job["name"], "schedule": job.get("schedule_display")},
    })


def _job_state_result(updated: Dict[str, Any]) -> str:
    _notify_provider_jobs_changed_safe()
    return _dumps({"success": True, "job": _format_job(updated)})


def _refreshed_job_view(job_id: str) -> Dict[str, Any]:
    """Re-read so the response reflects the post-run last_run_at/last_status."""
    return _format_job(get_job(job_id) or {"id": job_id})


def _action_run(job: Dict[str, Any], a: Dict[str, Any]) -> str:
    job_id = job["id"]
    extra_prompt = a["prompt"] or None
    if extra_prompt:
        scan_error = _scan_cron_prompt(extra_prompt)
        if scan_error:
            return tool_error(scan_error, success=False)
    bg = _try_dispatch_background_run(job, session_id=a["session_id"], extra_prompt=extra_prompt)
    if bg is not None and bg.get("dispatched"):
        _notify_provider_jobs_changed_safe()
        result = _refreshed_job_view(job_id)
        result["executed"] = True
        result["execution_mode"] = "background"
        result["delegation_id"] = bg.get("delegation_id")
        return _dumps({
            "success": True,
            "job": result,
            "note": (
                "The job is running in the background. You and the "
                "user can keep working; its outcome re-enters the "
                "conversation as a new message when it finishes. "
                "Do not wait or poll — just continue."),
        })
    if bg is not None:
        exec_result = bg
    else:
        forwarded = _forward_relay_fronted_run(job, extra_prompt=extra_prompt)
        if forwarded is not None:
            return forwarded
        exec_result = _execute_job_now(job, extra_prompt=extra_prompt)
    claimed = exec_result.get("claimed", False)
    if claimed:
        _notify_provider_jobs_changed_safe()
    result = _refreshed_job_view(job_id)
    result["executed"] = claimed
    result["execution_success"] = exec_result.get("success", False)
    if not claimed:
        result["execution_skipped"] = exec_result.get("error") or (
            "Already being fired by the scheduler; not run again.")
    elif exec_result.get("error"):
        result["execution_error"] = exec_result["error"]
    return _dumps({"success": True, "job": result})


def _pick(updates: Dict[str, Any], job: Dict[str, Any], key: str) -> Any:
    """Effective value of ``key`` after this update: pending update wins over the stored job."""
    return updates[key] if key in updates else job.get(key)


def _update_core_fields(job: Dict[str, Any], a: Dict[str, Any], updates: Dict[str, Any]) -> Optional[str]:
    """prompt / name / deliver / skills / model pins; returns an error string or None."""
    prompt, deliver, skill, skills = a["prompt"], a["deliver"], a["skill"], a["skills"]
    if prompt is not None:
        scan_error = _scan_cron_prompt(prompt)
        if scan_error:
            return scan_error
        updates["prompt"] = prompt
    if a["name"] is not None and a["name"].strip():
        updates["name"] = a["name"]
    if deliver is not None:
        bot_chat_error = _validate_bot_chat_deliver(_normalize_deliver_param(deliver))
        if bot_chat_error:
            return bot_chat_error
        updates["deliver"] = _resolve_cron_context_deliver(_normalize_deliver_param(deliver))
    if a["failure_deliver"] is not None:
        _norm_fd = _normalize_deliver_param(a["failure_deliver"])
        if _norm_fd:
            bot_chat_error = _validate_bot_chat_deliver(_norm_fd)
            if bot_chat_error:
                return bot_chat_error
            _norm_fd = _resolve_cron_context_deliver(_norm_fd)
        updates["failure_deliver"] = _norm_fd
    if skills is not None or skill is not None:
        canonical_skills = _canonical_skills(skill, skills)
        updates["skills"] = canonical_skills
        updates["skill"] = canonical_skills[0] if canonical_skills else None
    if a["model"] is not None:
        updates["model"] = _normalize_optional_job_value(a["model"])
    if a["provider"] is not None:
        updates["provider"] = _normalize_optional_job_value(a["provider"])
    if a["base_url"] is not None:
        updates["base_url"] = _normalize_optional_job_value(a["base_url"], strip_trailing_slash=True)
    if a["reasoning_effort"] is not None:
        updates["reasoning_effort"] = a["reasoning_effort"]
    return _validate_cron_base_url(_pick(updates, job, "provider"), _pick(updates, job, "base_url"))


def _update_script_fields(job: Dict[str, Any], a: Dict[str, Any], updates: Dict[str, Any]) -> Optional[str]:
    """script / monitor_script / monitor_url (empty string clears); returns an error string or None."""
    monitor_script, monitor_url = a["monitor_script"], a["monitor_url"]
    for field, value in (("script", a["script"]), ("monitor_script", monitor_script)):
        if value is not None:
            if value:
                path_error = _validate_cron_script_path(value)
                if path_error:
                    return path_error
            updates[field] = _normalize_optional_job_value(value) if value else None
    if monitor_url is not None:
        updates["monitor_url"] = _normalize_optional_job_value(monitor_url) if monitor_url else None
    if (monitor_script is not None or monitor_url is not None) and (
        _pick(updates, job, "monitor_script") and _pick(updates, job, "monitor_url")):
        return("monitor_script and monitor_url are mutually exclusive — clear one before setting the other.")
    return None


def _update_context_from(job: Dict[str, Any], a: Dict[str, Any], updates: Dict[str, Any]) -> Optional[str]:
    """context_from / continuity: empty string / list clears; otherwise every ref must
    exist. Stored as a list (or None) to match create_job()."""
    context_from, continuity = a["context_from"], a["continuity"]
    if context_from is None and continuity is None:
        return None
    if context_from is None:
        context_from = list(job.get("context_from") or [])
    refs = _clean_str_list(context_from)
    if continuity is not None:
        refs = _apply_continuity(refs, continuity) or []
    if refs:
        ref_error = _validate_context_from_refs(refs)
        if ref_error:
            return ref_error
    updates["context_from"] = refs or None
    return None


def _update_run_fields(job: Dict[str, Any], a: Dict[str, Any], updates: Dict[str, Any]) -> Optional[str]:
    """enabled_toolsets / attach_to_session / workdir / no_agent / repeat / schedule."""
    if a["enabled_toolsets"] is not None:
        updates["enabled_toolsets"] = a["enabled_toolsets"] or None
    if a["attach_to_session"] is not None:
        updates["attach_to_session"] = bool(a["attach_to_session"])
    if a["workdir"] is not None:
        updates["workdir"] = _normalize_optional_job_value(a["workdir"]) or None
    if a["no_agent"] is not None:
        target_no_agent = bool(a["no_agent"])
        if target_no_agent and not _pick(updates, job, "script"):
            return (
                "Cannot set no_agent=True on a job without a script. "
                "Set `script` in the same update, or on the job first.")
        updates["no_agent"] = target_no_agent
    if a["repeat"] is not None:
        from cron.jobs import normalize_repeat_value
        repeat_state = dict(job.get("repeat") or {})
        repeat_state["times"] = normalize_repeat_value(a["repeat"])
        updates["repeat"] = repeat_state
    if a["schedule"] is not None:
        parsed_schedule = parse_schedule(a["schedule"])
        updates["schedule"] = parsed_schedule
        updates["schedule_display"] = parsed_schedule.get("display", a["schedule"])
        if job.get("state") != "paused":
            updates["state"] = "scheduled"
            updates["enabled"] = True
    return None


_UPDATE_STEPS = (_update_core_fields, _update_script_fields, _update_context_from, _update_run_fields)


def _action_update(job: Dict[str, Any], a: Dict[str, Any]) -> str:
    updates: Dict[str, Any] = {}
    for step in _UPDATE_STEPS:
        error = step(job, a, updates)
        if error:
            return tool_error(error, success=False)
    if not updates:
        return tool_error("No updates provided.", success=False)
    updated = update_job(job["id"], updates)
    _notify_provider_jobs_changed_safe()
    return _dumps(_with_guidance(
        {"success": True, "job": _format_job(updated)}, updated, _normalize_deliver_param(a["deliver"])))


_JOBLESS_ACTIONS = {"create": _action_create, "list": _action_list}
_JOB_ACTIONS = {
    "remove": _action_remove, "update": _action_update,
    "run": _action_run, "run_now": _action_run, "trigger": _action_run,
    "pause": lambda job, a: _job_state_result(pause_job(job["id"], reason=a["reason"])),
    "resume": lambda job, a: _job_state_result(resume_job(job["id"])),
}


def _resolve_job_or_error(job_id: str):
    """``(job, None)`` or ``(None, json_error)`` for a job_id/name reference."""
    try:
        job = resolve_job_ref(job_id)
    except AmbiguousJobReference as exc:
        return None, _dumps({
            "success": False,
            "error": str(exc),
            "matches": [
                {"id": m["id"], "name": m.get("name"), "schedule": m.get("schedule_display"), "next_run_at": m.get("next_run_at")}
                for m in exc.matches
            ],
        })
    if not job:
        return None, _dumps(
            {"success": False, "error": f"Job with ID or name '{job_id}' not found. Use cronjob(action='list') to inspect jobs."},
        )
    return job, None


def cronjob(
    action: str,
    job_id: Optional[str] = None,
    prompt: Optional[str] = None,
    schedule: Optional[str] = None,
    name: Optional[str] = None,
    repeat: Optional[int] = None,
    deliver: Optional[str] = None,
    include_disabled: bool = False,
    skill: Optional[str] = None,
    skills: Optional[List[str]] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    reason: Optional[str] = None,
    script: Optional[str] = None,
    context_from: Optional[Union[str, List[str]]] = None,
    continuity: Optional[bool] = None,
    enabled_toolsets: Optional[List[str]] = None,
    workdir: Optional[str] = None,
    no_agent: Optional[bool] = None,
    attach_to_session: Optional[bool] = None,
    monitor_script: Optional[str] = None,
    monitor_url: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    failure_deliver: Optional[Union[str, List[str]]] = None,
    task_id: str = None,
    session_id: Optional[str] = None,
    paused: bool = False,
    paused_reason: Optional[str] = None) -> str:
    """Unified cron job management tool."""
    a = dict(locals())
    del a["task_id"]
    try:
        normalized = (action or "").strip().lower()
        handler = _JOBLESS_ACTIONS.get(normalized)
        if handler is not None:
            return handler(a)
        if not job_id:
            return tool_error(f"job_id is required for action '{normalized}'", success=False)
        job, error = _resolve_job_or_error(job_id)
        if error is not None:
            return error
        handler = _JOB_ACTIONS.get(normalized)
        if handler is None:
            return tool_error(f"Unknown cron action '{action}'", success=False)
        return handler(job, a)
    except Exception as e:
        return tool_error(str(e), success=False)


CRONJOB_SCHEMA = {
    "name": "cronjob_manage",
    "description": """Manage scheduled cron jobs: action='create' schedules a job from a prompt and/or skills; 'list' inspects jobs; 'update'/'pause'/'resume'/'remove' manage one by job_id (always list first — never guess job IDs); 'run' fires a job immediately in the BACKGROUND (returns a handle at once, outcome re-enters the conversation when done — do not wait or poll; optional 'prompt' adds transient context for that fire only).

Jobs run in a fresh session with no current-chat context, so prompts must be self-contained, and the agent's FINAL RESPONSE is what gets delivered — cron runs are autonomous and cannot ask questions. Prefer updating an existing job over creating near-duplicates.""",
    "parameters": {
        "type": "object",
        "properties": {
            "paused": {"type": "boolean", "description": "Create only: persist disabled atomically. Resume to schedule; explicit run remains available. Default false."},
            "paused_reason": {"type": "string", "description": "Create only: auditable reason; requires paused=true."},
            "action": {
                "type": "string",
                "description": "One of: create, list, update, pause, resume, remove, run. When action=create, the 'schedule' and 'prompt' fields are REQUIRED."
            },
            "job_id": {
                "type": "string",
                "description": "Required for update/pause/resume/remove/run"
            },
            "prompt": {
                "type": "string",
                "description": "For create: the full self-contained prompt (paired with any skills as the task instruction). For run: optional transient context for that single fire (never persisted)."
            },
            "schedule": {
                "type": "string",
                "type": "string",
                "description": "REQUIRED for create. Schedule forms: (1) recurring interval — '30m', 'every 2h', 'every hour' (EVERY 30 minutes / 2 hours / hour, forever by default); (2) explicit one-shot by duration — 'in 30m', 'in 2h' (fires ONCE that far from now; use this for 'remind me in N minutes' — do NOT hand-compute an absolute timestamp); (3) natural day/time — 'every monday 9am', 'weekdays at 9am', 'every day at 9am' (recurring weekly/daily); (4) cron syntax — '0 9 * * *' (daily 9am); (5) absolute one-shot — ISO timestamp '2026-06-01T09:00:00'."
            },
            "name": {
                "type": "string",
                "description": "Optional human-friendly name"
            },
            "repeat": {
                "type": "integer",
                "description": "Optional repeat count. Omit for defaults (once for one-shot, forever for recurring)."
            },
            "deliver": {
                "type": "string",
                "description": "Where the job's output is POSTED as a one-way message (the job itself always runs in a fresh session with no chat context). Omit to address the chat/topic this job was created from. Otherwise: 'local' (save only, no delivery), 'all' (every connected home channel, resolved at fire time), 'bot-chat' or 'bot-chat:<profile>' (inject into a Bot Chat as a real message), or platform:chat_id:thread_id (e.g. 'telegram:-1001234567890:17585'). Comma-combine like 'origin,all'."
            },
            "failure_deliver": {
                "type": "string",
                "description": "Optional override target for FAILURE notices only (same grammar as deliver). When set, engine failure/interruption notices go here instead of the deliver target; 'local' suppresses them entirely (state still recorded in cron list/run history). Use for jobs delivering into shared channels where failure noise is unwanted. Omit = failures follow deliver (default). On update, '' clears."
            },
            "skills": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional ordered skill names loaded before the cron prompt. On update, [] clears."
            },
            "script": {
                "type": "string",
                "description": f"Optional script run each tick; stdout is injected into the agent's prompt as context (with no_agent=True the script IS the job). Relative paths resolve under {display_arkos_home()}/scripts/; .sh/.bash via bash, else Python. On update, '' clears."
            },
            "monitor": {
                "type": "string",
                "description": "Optional change-detector that gates the agent: an http(s) URL (fetched each tick) or a script path (same rules as `script`, run each tick) — cheap, no LLM. Output identical to the previous tick skips the agent run entirely; changed output wakes the agent with a diff injected into the prompt. First tick always runs (baseline). Output must be deterministic (no timestamps) or every tick looks changed. Incompatible with no_agent. On update, '' clears."
            },
            "no_agent": {
                "type": "boolean",
                "default": False,
                "description": "True = no LLM: the scheduler runs `script` (required) on schedule and delivers its stdout verbatim; empty stdout sends nothing (watchdog pattern). Use for script-only pings with fixed output; keep False for anything needing reasoning."
            },
            "context_from": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional job ID(s) whose most recent completed output is injected as context each run — chains jobs (A collects, B processes). For a job's OWN previous output prefer `continuity`. On update, [] clears."
            },
            "continuity": {
                "type": "boolean",
                "description": "True = each run sees the job's own previous output, so it can dedupe and continue where it left off (scouts, monitors, incremental digests). Default false. On update, false turns it off."
            },
            "enabled_toolsets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional toolset names to restrict the job's agent to (e.g. [\"web\", \"terminal\"]) — cuts token overhead. Infer from the prompt. Omit for all default tools. On update, [] clears."
            },
            "workdir": {
                "type": "string",
                "description": "Optional absolute existing path to run the job from: injects that directory's AGENTS.md/context files and anchors terminal/file tools there. On update, '' clears."
            },
            "attach_to_session": {
                "type": "boolean",
                "description": "True = the job's delivery is CONTINUABLE — the user can reply and the agent has the brief in context (threads on thread-capable platforms, mirrored into the DM elsewhere). Use for conversational recurring jobs (briefings); leave unset for fire-and-forget alerts. Scope: the job's own conversation only — the origin chat, the home-channel fallback when deliver='origin' captured no origin (script-created jobs), or the job's single explicit platform:chat target (this flag is the only way to attach an explicit target). Broadcast targets are never attached; no effect when deliver='local'."
            },
        },
        "required": ["action"]
    }
}


def check_cronjob_requirements() -> bool:
    """Available in interactive CLI mode and gateway/messaging platforms (the scheduler is
    internal; no crontab needed). Flags must be explicitly truthy via ``env_var_enabled``."""
    from utils import env_var_enabled
    return (
        env_var_enabled("ARKOS_INTERACTIVE")
        or env_var_enabled("ARKOS_GATEWAY_SESSION")
        or env_var_enabled("ARKOS_EXEC_ASK")
    )


_HANDLER_FORWARDED_ARGS = (
    "job_id", "prompt", "schedule", "name", "repeat", "deliver", "failure_deliver", "skill", "skills", "reason",
    "script", "context_from", "continuity", "enabled_toolsets", "workdir", "no_agent", "attach_to_session",
    "paused_reason")


def _cronjob_handler(args, **kw):
    """Model-tool dispatch: resolves the one model-facing ``monitor`` field into the stored
    ``monitor_script``/``monitor_url`` pair (legacy field names still accepted)."""
    _mon_script, _mon_url = _split_monitor_arg(args.get("monitor"), args.get("monitor_script"), args.get("monitor_url"))
    return cronjob(
        action=args.get("action", ""),
        include_disabled=args.get("include_disabled", True),
        monitor_script=_mon_script,
        monitor_url=_mon_url,
        task_id=kw.get("task_id"),
        session_id=kw.get("session_id"),
        paused=args.get("paused", False),
        **{key: args.get(key) for key in _HANDLER_FORWARDED_ARGS},
    )


registry.register(
    name="cronjob_manage",
    toolset="cronjob",
    schema=CRONJOB_SCHEMA,
    handler=_cronjob_handler,
    check_fn=check_cronjob_requirements,
    emoji="⏰",
)


import re  # noqa: F401,E402
