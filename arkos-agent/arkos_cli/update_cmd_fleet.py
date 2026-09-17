"""Gateway fleet restart + post-update verification for ``arkos update``.

Split out of ``arkos_cli/update_cmd.py``; every name is re-imported there so
``arkos_cli.update_cmd.<name>`` keeps resolving/monkeypatching. Origin helpers are
imported lazily inside each function (no import cycle; test patches stay effective).
"""

import logging
from contextlib import suppress
import os
import subprocess
import sys
import time as _time
from dataclasses import dataclass, field
from pathlib import Path

from arkos_cli.update_cmd_common import _best_effort
from arkos_cli.update_inventory import _gateway_service_matches_profile

logger = logging.getLogger("arkos_cli.update_cmd")

_FLEET_RESTART_PENDING_NAME = "fleet_restart_pending"

_FRESH_RESTART_SUPERVISORS = frozenset({"systemd", "launchd", "service", "s6"})

_SYSTEMD_SCOPES = (("user", ["systemctl", "--user"]), ("system", ["systemctl"]))
_LIST_GATEWAY_UNITS = ["list-units", "arkos-gateway*", "arkos-serve*", "--plain", "--no-legend", "--no-pager"]


def _write_gateway_update_exit_code(ok: bool) -> None:
    from arkos_cli.update_cmd import get_arkos_home
    path = get_arkos_home() / ".update_exit_code"
    with suppress(OSError):
        path.write_text("0" if ok else "1", encoding="utf-8")


def _fleet_restart_pending_marker_path() -> Path:
    """ARKOS_HOME breadcrumb for a pull that has not yet restarted the fleet."""
    from arkos_cli.update_cmd import get_arkos_home
    return get_arkos_home() / _FLEET_RESTART_PENDING_NAME


def _write_fleet_restart_pending_marker(*, expected_sha: str = "") -> None:
    """Drop the pull→restart obligation breadcrumb. Never raises."""
    from arkos_cli.update_cmd import _m
    path = _fleet_restart_pending_marker_path()
    if _m()._pytest_owns_live_checkout(path.parent):
        logger.debug("Skipping fleet-restart-pending marker under pytest (live checkout)")
        return
    try:
        lines = [f"started={_time.time()}", f"pid={os.getpid()}"]
        if expected_sha:
            lines.append(f"expected_sha={expected_sha}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.debug("Could not write fleet-restart-pending marker: %s", exc)


def _clear_fleet_restart_pending_marker() -> None:
    """Remove the pull→restart obligation breadcrumb. Never raises."""
    from arkos_cli.update_cmd import _m
    _m()._clear_marker_file(_fleet_restart_pending_marker_path(), label="fleet-restart-pending")


def _current_checkout_sha() -> str | None:
    """Current on-disk checkout HEAD, or None if it cannot be resolved."""
    from arkos_cli.update_cmd import _capture_head_sha, _m
    try:
        from arkos_cli.build_info import get_code_identity
        sha = (get_code_identity(refresh=True) or {}).get("sha")
        return str(sha) if sha else None
    except Exception:
        return _capture_head_sha(["git"], _m().PROJECT_ROOT)


def _receipt_looks_unfinished(receipt: dict) -> bool:
    """True when *receipt* is from an update that did not finish cleanly.

    The command boundary stamps a ``stop_reason`` on every receipt, including clean
    ones (``completed at command boundary``, ``sys.exit(0)``); it must not make a
    successful receipt look unfinished, or the next ``arkos update`` retriggers
    ``fleet_restart_pending`` from pre-pull plan SHAs.
    """
    exit_code = receipt.get("exit_code")
    outcome = receipt.get("outcome")
    if exit_code not in (0, None) or outcome in ("failed", "partial", "running"):
        return True
    gateway_restart = receipt.get("gateway_restart")
    if isinstance(gateway_restart, dict) and gateway_restart.get("incomplete"):
        return True
    succeeded = exit_code == 0 or outcome == "success"
    return bool(receipt.get("stop_reason")) and not succeeded


def _receipt_reports_stale_runtime(expected_sha: str | None = None) -> bool:
    """True when ``update_receipts/latest.json`` records a runtime SHA skew.

    Prefer the post-restart ``fleet`` matrix. ``plan.runtimes[].code_sha`` is captured
    *before* the pull, so a finished update's plan always looks stale and must not
    retrigger a restart; consult it only for an unfinished receipt..
    """
    from arkos_cli.update_cmd import _current_checkout_sha
    try:
        from arkos_cli.update_receipt import read_latest_receipt
        receipt = read_latest_receipt()
    except Exception:
        receipt = None
    if not isinstance(receipt, dict):
        return False
    expected_sha = expected_sha or _current_checkout_sha()
    if not expected_sha:
        return False

    def _sha_mismatch(code_sha) -> bool:
        return bool(code_sha) and str(code_sha) != str(expected_sha)

    fleet = receipt.get("fleet")
    if isinstance(fleet, list) and fleet:
        return any(
            isinstance(entry, dict)
            and (entry.get("state") == "stale" or _sha_mismatch(entry.get("code_sha")))
            for entry in fleet
        )

    if not _receipt_looks_unfinished(receipt):
        return False
    plan = receipt.get("plan")
    if not isinstance(plan, dict):
        return False
    return any(
        isinstance(runtime, dict) and _sha_mismatch(runtime.get("code_sha"))
        for runtime in plan.get("runtimes") or []
    )


def _live_fleet_covers_receipt(expected_sha: str | None) -> bool:
    """Require current successors for every recorded runtime, not just any live row.

    A PID changes on restart; the stable identity is (runtime kind, profile).
    The gateway matrix cannot vouch for serve/dashboard or unidentified runtimes.
    Keep the historical receipt intact: a manual restart is not a successful update.
    """
    if not expected_sha:
        return False
    from arkos_cli.update_receipt import collect_fleet_versions, read_latest_receipt

    try:
        receipt = read_latest_receipt() or {}
        plan = receipt.get("plan") or {}
        runtimes = plan.get("runtimes") or []
        recorded_fleet = receipt.get("fleet") or []
        owed = set()
        entries: list[tuple[object, str | None]] = [(entry, None) for entry in runtimes]
        entries.extend((entry, "gateway") for entry in recorded_fleet)
        for entry, default_kind in entries:
            if not isinstance(entry, dict):
                return False
            kind = entry.get("kind", default_kind)
            profile = entry.get("profile")
            if kind != "gateway" or not profile or profile == "unknown":
                return False
            owed.add((kind, profile))
        if not owed:
            return False
        fleet = collect_fleet_versions()
        if not fleet or any(
            row.get("state") != "current" or row.get("code_sha") != expected_sha
            for row in fleet
        ):
            return False
        return owed <= {("gateway", row.get("profile")) for row in fleet}
    except Exception as exc:
        logger.debug("Could not reconcile pending fleet identities: %s", exc)
        return False


def _pending_fleet_restart_needed() -> bool:
    """Reconcile old restart obligations against current, identity-matched gateways."""
    from arkos_cli.update_cmd import _current_checkout_sha

    with suppress(OSError):
        if _fleet_restart_pending_marker_path().is_file():
            return True
    if not _receipt_reports_stale_runtime():
        return False
    return not _live_fleet_covers_receipt(_current_checkout_sha())


def _warn_pending_fleet_restart(*, startup: bool = False) -> None:
    """Print the specific interrupted-update fleet-restart warning."""
    stream = sys.stderr if startup else sys.stdout
    print("⚠ A previous `arkos update` pulled new code but did not restart running gateways.", file=stream)
    print("  Gateways may still be serving pre-update modules (mixed sys.modules).", file=stream)
    if startup:
        print("  Run `arkos update` or `arkos gateway restart`.", file=stream)


def _warn_pending_fleet_restart_on_startup() -> None:
    """Cheap CLI-startup hint. Never restarts; never raises."""
    with suppress(Exception):
        if _pending_fleet_restart_needed():
            _warn_pending_fleet_restart(startup=True)


def _systemd_gateway_unit_listings(on_list_timeout=None):
    """Yield ``(scope, scope_cmd, list-units CompletedProcess)`` per systemd scope that answered.

    A missing systemctl skips the scope silently; a listing timeout skips it after
    ``on_list_timeout(scope, exc)`` (when given) so the other scope is still processed.
    """
    for scope, scope_cmd in _SYSTEMD_SCOPES:
        try:
            result = _systemctl(scope_cmd + _LIST_GATEWAY_UNITS, timeout=10)
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired as exc:
            if on_list_timeout is not None:
                on_list_timeout(scope, exc)
            continue
        yield scope, scope_cmd, result


def _needs_sudo(scope: str) -> bool:
    return (
        scope == "system"
        and hasattr(os, "geteuid")
        and os.geteuid() != 0
    )


def _restart_systemd_gateway_units_best_effort(failed: list, listings) -> None:
    """Best-effort ``systemctl restart`` of every arkos-gateway/serve unit."""
    answered = set()
    for scope, scope_cmd, result in listings:
        answered.add(scope)
        if result.returncode != 0:
            failed.append(f"systemd-{scope} (listing failed)")
            continue

        def process_unit(svc_name: str, _scope=scope, _cmd=scope_cmd) -> None:
            manage_cmd = list(_cmd) + ["--no-ask-password"]
            if _needs_sudo(_scope):
                manage_cmd = ["sudo", "-n"] + manage_cmd
            result = _systemctl_reset_and_restart(manage_cmd, svc_name, scope_cmd=_cmd)
            if result.returncode != 0 or not _wait_for_service_active(_cmd, svc_name):
                failed.append(svc_name)

        _for_each_systemd_gateway_unit(
            result.stdout,
            process_unit=process_unit,
            on_unit_timeout=lambda svc_name, exc: failed.append(svc_name),
        )
    failed.extend(f"systemd-{scope} (listing unavailable)" for scope, _ in _SYSTEMD_SCOPES if scope not in answered)


def _run_pending_fleet_restart() -> bool:
    """Catch-up restart for gateways left on pre-update code. Never raises.

    True when all discovered targets recovered (or none exist); False if incomplete..
    """
    from arkos_cli.update_cmd import _m
    print("→ Restarting gateways left on pre-update code...")
    with suppress(Exception):
        _m()._purge_stale_arkos_modules()
    try:
        from arkos_cli.gateway import (
            find_gateway_pids, is_macos, is_windows, kill_gateway_processes, supports_systemd_services,
            _wait_for_gateway_exit,
        )
    except Exception as exc:
        _warn_gateway_restart_phase_aborted(exc, None)
        return False

    try:
        pids = list(find_gateway_pids(all_profiles=True))
    except Exception as exc:
        logger.debug("Pending fleet restart: gateway probe failed: %s", exc)
        pids = None

    failed: list = []
    try:
        systemd_listings = list(_systemd_gateway_unit_listings()) if supports_systemd_services() else None
        if pids != []:
            try:
                leftover = list(find_gateway_pids(all_profiles=True))
            except Exception:
                leftover = list(pids or [])
            if leftover:
                with _best_effort('Pending fleet restart: PID stop failed: %s'):
                    kill_gateway_processes(all_profiles=True)
                    _wait_for_gateway_exit(timeout=5.0, force_after=None)
        if systemd_listings is not None:
            _restart_systemd_gateway_units_best_effort(failed, systemd_listings)
        if is_macos():
            try:
                _restart_macos_launchd_gateways([], failed, 45.0, require_supervision=True)
            except Exception as exc:
                logger.debug("Pending fleet restart: launchd failed: %s", exc)
                failed.append("launchd")
        if is_windows():
            try:
                from arkos_cli import gateway_windows
                if gateway_windows.is_installed():
                    gateway_windows.restart()
            except Exception as exc:
                logger.debug("Pending fleet restart: Windows failed: %s", exc)
                failed.append("windows-gateway")
        if failed:
            _warn_incomplete_gateway_fleet_restart(failed)
            return False
        print("  ✓ Pending fleet restart completed.")
        return True
    except Exception as exc:
        try:
            surviving = list(find_gateway_pids(all_profiles=True))
        except Exception:
            surviving = pids
        _warn_gateway_restart_phase_aborted(exc, surviving)
        return False


def _apply_pending_fleet_restart_catchup() -> None:
    """On an already-up-to-date ``arkos update``, finish a skipped restart.

    No-op when nothing is pending; exits 1 on incomplete catch-up so automation
    does not treat the fleet as healthy.
    """
    from arkos_cli.update_cmd import _run_pending_fleet_restart
    if not _pending_fleet_restart_needed():
        return
    print()
    _warn_pending_fleet_restart()
    print("→ Running the pending fleet restart...")
    if _run_pending_fleet_restart():
        _clear_fleet_restart_pending_marker()
        return
    print("  ⚠ Fleet restart incomplete. Recover with: arkos gateway restart")
    sys.exit(1)


def _systemctl(cmd: list, *, timeout: float):
    """Run a systemctl (or sudo systemctl) invocation, capturing utf-8 text with a timeout."""
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


_SYSTEMCTL_RESTART_TIMEOUT_MAX = (2**31 - 1) // 1000 - 1


def _systemd_restart_timeout(scope_cmd: list, svc_name: str, *, start_only: bool = False) -> float:
    """Outwait the unit's stop + start budgets, not just the systemctl client.

    A client timeout does not cancel the manager's queued restart. Unknown or
    infinite limits use systemd's usual 90s per phase so automation stays bounded.
    Custom ExecStop chains or EXTEND_TIMEOUT_USEC can still exceed this budget;
    genuine timeouts must continue through the existing per-unit failure path.
    """
    from gateway.shutdown_forensics import parse_systemd_duration_to_us

    budgets = {"TimeoutStartUSec": 90.0}
    if not start_only:
        budgets["TimeoutStopUSec"] = 90.0
    try:
        show = _systemctl(
            scope_cmd + ["show", svc_name, "--property=TimeoutStopUSec,TimeoutStartUSec"],
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return sum(budgets.values()) + 15.0
    if show.returncode == 0:
        for line in (show.stdout or "").splitlines():
            key, _, raw = line.partition("=")
            if key in budgets:
                try:
                    raw = raw.strip()
                    duration = int(raw) if raw.isascii() and raw.isdigit() else parse_systemd_duration_to_us(raw)
                    if duration is not None and duration > 0:
                        budgets[key] = duration / 1_000_000
                except (ValueError, OverflowError):
                    pass
    return min(sum(budgets.values()) + 15.0, _SYSTEMCTL_RESTART_TIMEOUT_MAX)


def _systemctl_reset_and_restart(manage_cmd: list, svc_name: str, *, scope_cmd: list | None = None):
    """``reset-failed`` then ``restart``: a unit parked in failed state by systemd's own
    auto-restart can wedge a plain ``restart`` against RestartSec backoff and stay dead."""
    timeout = _systemd_restart_timeout(scope_cmd if scope_cmd is not None else manage_cmd, svc_name)
    _systemctl(manage_cmd + ["reset-failed", svc_name], timeout=10)
    return _systemctl(manage_cmd + ["restart", svc_name], timeout=timeout)


def _is_arkos_gateway_unit(unit: str) -> bool:
    """Exact base unit or hyphenated profile family only: ``startswith("arkos-serve")``
    would accept ``arkos-server.service``."""
    return (
        unit == "arkos-gateway.service"
        or unit.startswith("arkos-gateway-")
        or unit == "arkos-serve.service"
        or unit.startswith("arkos-serve-")
    )


def _for_each_systemd_gateway_unit(list_units_stdout: str, *, process_unit, on_unit_timeout) -> None:
    """Process each arkos-gateway*/arkos-serve* unit from ``systemctl list-units``.

    ``TimeoutExpired`` from ``process_unit`` is isolated per unit via ``on_unit_timeout``
    so one wedged systemctl call cannot abort the rest of the fleet..
    """
    for line in (list_units_stdout or "").strip().splitlines():
        parts = line.split()
        if not parts:
            continue
        unit = parts[0]
        if not unit.endswith(".service") or not _is_arkos_gateway_unit(unit):
            continue
        svc_name = unit.removesuffix(".service")
        try:
            process_unit(svc_name)
        except subprocess.TimeoutExpired as exc:
            on_unit_timeout(svc_name, exc)


def _service_unit_supports_graceful_sigusr1_restart(svc_name: str) -> bool:
    """Whether *svc_name* wires SIGUSR1 to a graceful drain-then-restart.

    Only ``arkos-gateway*`` runs ``gateway/run.py`` (the handler); SIGUSR1 would just
    kill ``arkos-serve*`` and burn the drain budget, so those go straight to the blunt
    restart. Same exact/hyphenated shape as ``_for_each_systemd_gateway_unit`` so a
    near-prefix unit like ``arkos-gatewayd`` is never signalled..
    """
    return svc_name == "arkos-gateway" or svc_name.startswith("arkos-gateway-")


def _warn_incomplete_gateway_fleet_restart(failed_units: list) -> None:
    """Print an explicit incomplete-update warning for unrestarted units."""
    from arkos_cli.gateway import is_macos
    if not failed_units:
        return
    ordered = list(dict.fromkeys(failed_units))
    print()
    print("⚠ Update incomplete — some units were not restarted:")
    for name in ordered:
        print(f"    - {name}")
    if is_macos():
        print("  Listed services may be deregistered from launchd, or still")
        print("  running pre-update code (mixed sys.modules). Recover with:")
        print("    arkos gateway status")
        print("    launchctl list | grep <label>")
        print("    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/<label>.plist")
        return
    print("  Skipped units may still be running pre-update code (mixed")
    print("  sys.modules). Restart them manually, then verify:")
    print("    arkos gateway status")
    if any(not name.startswith("ai.arkos.") for name in ordered):
        print("    systemctl --user restart <unit>   # user-scope")
        print("    sudo systemctl restart <unit>     # system-scope")
    if any(name.startswith("ai.arkos.") for name in ordered):
        print("    launchctl kickstart -k gui/$UID/<label>   # macOS (or user/$UID)")


def _restart_launchd_gateway_after_update(*, supervision_verify: bool = True) -> tuple[list, list]:
    """Restart the invoking profile's launchd gateway after an update.

    No ``launchctl list`` gating: a booted-out job (plist present, definition
    deregistered) fails it, and it can exit non-zero while the job is alive — gating on it
    silently skipped the restart yet printed "Update complete!". When the plist exists
    ``launchd_restart()`` always runs; every failure path is loud with a manual recovery
    command. Returns ``(restarted_labels, failed_labels)``; with ``supervision_verify``
    success also requires a fresh supervised PID ("the call returned" is not "supervised").

    The restart used to be gated on ``launchctl list <label>``
    exiting 0. A *booted-out* job — plist present, definition deregistered from launchd (crashed helper,
    manual bootout, failed prior update) — fails that check, so the whole branch silently skipped: no
    restart, no message, ``KeepAlive`` unable to revive a definition launchd no longer knows, and the update
    still printed "Update complete!".
    """
    from arkos_cli.gateway import (
        get_launchd_label, get_launchd_plist_path, launchd_restart, wait_for_launchd_gateway_supervision,
    )
    current_label = get_launchd_label()
    try:
        if not get_launchd_plist_path().exists():
            return [], []
        try:
            launchd_restart()
        except subprocess.CalledProcessError as e:
            stderr = (getattr(e, "stderr", "") or "").strip()
            print(
                f"  ⚠ Gateway restart failed: {stderr}\n"
                "    The gateway may be DOWN on pre-update code. "
                "Recover manually: arkos gateway restart"
            )
            return [], [current_label]
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(
            "  ⚠ Could not restart the gateway "
            f"({e.__class__.__name__}: {e}).\n"
            "    Recover manually: arkos gateway restart"
        )
        return [], [current_label]

    if not supervision_verify:
        return [current_label], []

    if wait_for_launchd_gateway_supervision(label=current_label):
        return [current_label], []
    print(
        f"  ✗ {current_label} restarted but launchd is not supervising it.\n"
        "    Check logs, then: arkos gateway restart"
    )
    return [], [current_label]


def _restart_macos_launchd_gateways(
    restarted_services: list, failed_or_stale_units: list, drain_budget: float, *, require_supervision: bool = False,
) -> None:
    """Restart every launchd-managed gateway after an update (macOS).

    The pull is shared across profiles, so every ``ai.arkos.gateway*`` LaunchAgent
    must reload it or siblings stay on pre-update ``sys.modules`` (systemd parity).
    Invoking profile uses ``launchd_restart``; siblings get the same drain-first
    sequence with their domain (``gui/<uid>`` vs ``user/<uid>``) resolved per label so
    none is kickstarted in the wrong domain. ``TimeoutExpired`` is isolated per label..
    The invoking profile keeps the existing ``launchd_restart`` treatment (self-restart request → graceful
    drain → kickstart). ``subprocess.TimeoutExpired`` is isolated per label so one wedged launchctl call
    cannot leave the rest of the fleet on old code.
    """
    from arkos_cli.gateway import (
        get_launchd_label, get_launchd_plist_path, launchd_gateway_labels_for_install, _graceful_restart_via_sigusr1, _launchd_kickstart,
        _locate_launchd_gateway_service, _wait_for_launchd_service_pid,
    )
    if require_supervision:
        listing = subprocess.run(["launchctl", "list"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        if listing.returncode != 0:
            failed_or_stale_units.append("launchd (listing failed)")
            return
    _restarted, _failed = _restart_launchd_gateway_after_update(supervision_verify=True)
    restarted_services.extend(_restarted)
    failed_or_stale_units.extend(_failed)
    current_label = get_launchd_label()

    for label in launchd_gateway_labels_for_install():
        if label == current_label:
            continue
        try:
            domain, old_pid = _locate_launchd_gateway_service(label)
            if domain is None:
                if require_supervision and get_launchd_plist_path().with_name(f"{label}.plist").exists():
                    failed_or_stale_units.append(label)
                continue
            graceful_ok = False
            if old_pid is not None and old_pid > 0:
                print(f"  → {label}: draining (up to {int(drain_budget)}s)...")
                graceful_ok = _graceful_restart_via_sigusr1(old_pid, drain_timeout=drain_budget)
            if graceful_ok and _wait_for_launchd_service_pid(label, old_pid=old_pid, timeout=10.0, domain=domain):
                restarted_services.append(label)
                continue
            try:
                _launchd_kickstart(label, domain)
            except subprocess.CalledProcessError as e:
                stderr = (getattr(e, "stderr", "") or "").strip()
                failed_or_stale_units.append(label)
                print(
                    f"  ⚠ Failed to restart {label}: {stderr}\n"
                    f"    Recover manually: launchctl kickstart -k {domain}/{label}"
                )
                continue
            if _wait_for_launchd_service_pid(label, old_pid=old_pid, timeout=15.0, domain=domain):
                restarted_services.append(label)
            else:
                failed_or_stale_units.append(label)
                print(
                    f"  ✗ {label} failed to come back after restart.\n"
                    f"    Check logs, then: launchctl kickstart -k {domain}/{label}"
                )
        except subprocess.TimeoutExpired:
            failed_or_stale_units.append(label)
            print(f"  ⚠ launchctl timed out restarting {label}; continuing with remaining gateways")


def _surviving_gateway_pids_after_failed_restart():
    """Best-effort PIDs of gateways still running after the restart phase died.

    ``None`` when undeterminable (notably ``arkos_cli.gateway`` no longer importing
    under the replaced checkout). Callers treat ``None`` and non-empty as "assume
    stale"; only a positive empty result proves nothing needs restarting.
    """
    try:
        from arkos_cli.gateway import find_gateway_pids
        return list(find_gateway_pids(all_profiles=True))
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Could not probe for surviving gateways after update: %s", exc)
        return None


_MANUAL_GATEWAY_SKIP_REASON = (
    "manual gateway has no supervisor relaunch authority; left running for explicit operator restart"
)
_DESKTOP_SERVE_SKIP_REASON = (
    "desktop app owns and respawns this serve backend;"
    " the recovery pass must not restart it out from under its supervisor"
)
_SERVE_SKIP_REASON = (
    "no per-profile relaunch command reaches a serve/dashboard runtime; recovered by the fresh"
    " systemd unit pass when it owns a arkos-serve* unit, else left running for explicit"
    " operator restart"
)


def _gateway_recovery_partition(plan, *, skip_profiles: set[str] | None = None) -> tuple[dict[str, str], list[dict]]:
    """Partition pre-update runtimes into fresh-restart candidates and skips.

    Uses only the pre-checkout inventory: re-importing ``arkos_cli.gateway`` in the
    failing interpreter is what raises the original ``ImportError``. Returns
    ``(candidates, skipped)``: profile → supervisor for supervised gateways the fresh
    process may restart; every other inventoried runtime with an explicit reason so
    nothing vanishes silently. Skipped serve/dashboard is NOT unrecoverable: the fresh
    child's ``arkos-serve*`` systemd pass enumerates units from systemd; leftovers are
    caught by :func:`_surviving_pre_update_serve_runtimes`.
    """
    skip_profiles = skip_profiles or set()
    candidates: dict[str, str] = {}
    skipped: list[dict] = []
    with _best_effort('Could not prepare fresh gateway restart profiles: %s'):
        for runtime in getattr(plan, "runtimes", ()) or ():
            kind = getattr(runtime, "kind", None)
            profile = getattr(runtime, "profile", None)
            supervisor = getattr(runtime, "supervisor", None)
            if not isinstance(profile, str) or not profile:
                continue
            if kind == "gateway":
                if profile in skip_profiles:
                    continue
                if supervisor in _FRESH_RESTART_SUPERVISORS:
                    candidates.setdefault(profile, str(supervisor))
                    continue
                reason = _MANUAL_GATEWAY_SKIP_REASON
            elif kind in ("serve", "dashboard"):
                reason = _DESKTOP_SERVE_SKIP_REASON if supervisor == "desktop" else _SERVE_SKIP_REASON
            else:
                continue
            skipped.append({"profile": profile, "kind": str(kind), "supervisor": str(supervisor), "reason": reason})
    return candidates, skipped


def _warn_gateway_restart_phase_aborted(exc: BaseException, pids) -> None:
    """Print a recovery warning when the whole restart phase raised.

    Previously a blanket debug-logged ``except Exception`` erased every drain/restart
    line, so "Update complete!" exited 0 while the gateway kept serving pre-update
    modules and died on the next turn with an ImportError.

    prior patch: the gateway auto-restart phase was wrapped in a blanket ``except Exception`` that only
    logged at debug level, so an early failure (e.g. importing ``arkos_cli.gateway`` from the freshly
    pulled checkout) erased every drain/restart line from the update output.
    """
    print()
    print(f"⚠ Update incomplete — gateway auto-restart failed: {exc}")
    if pids:
        listed = ", ".join(str(pid) for pid in pids)
        print(f"  Gateway process(es) still running pre-update code: {listed}")
    else:
        print("  Any gateway still running is serving pre-update code")
        print("  (mixed sys.modules) against the updated checkout.")
    print("  Restart it manually, then verify:")
    print("    arkos gateway restart")
    print("    arkos gateway status")


def _drain_or_signal_gateway_for_update(pid: int, drain_budget: float, label: str) -> bool:
    """Three-way triage (shared by systemd and bare-process paths) for handing a
    running gateway over to new code. Returns True when signalled/stopped.

    1. Gateway is an ancestor of this process (auto-update cron inside the gateway
       tree): waiting is circular (gateway waits on in-flight work → cron session
       waits on update → update waits on gateway) and the 1800s force-drain cap burns.
       So fire-and-forget: signal restart and return; it completes once THIS process exits.
    2. Event loop provably wedged: SIGUSR1 can never drain it; bounded SIGTERM→SIGKILL.
    3. Live out-of-tree gateway: graceful SIGUSR1 drain up to ``drain_budget``.

    The wedged-loop probe cannot break it: the cron session posts activity every ~180s (process-tool poll
    return), so it is "actively waiting forever" and never marked wedged — the gateway burns the full
    force-drain cap (1800s) before killing its own updater's session..
    """
    from arkos_cli.gateway import (
        GATEWAY_LOOP_WEDGED, _escalate_wedged_gateway, _graceful_restart_via_sigusr1,
        _is_pid_ancestor_of_current_process, _request_gateway_self_restart, probe_gateway_loop_liveness,
    )
    if _is_pid_ancestor_of_current_process(pid):
        print(
            f"  → {label}: update is running inside this gateway's "
            "process tree — signalling restart and letting the gateway "
            "drain itself (avoids the cron-update deadlock)"
        )
        return _request_gateway_self_restart(pid)
    if probe_gateway_loop_liveness(pid) == GATEWAY_LOOP_WEDGED:
        print(f"  ⚠ {label}: gateway event loop is unresponsive — skipping drain, forcing a bounded stop...")
        _escalate_wedged_gateway(pid)
        return True
    print(f"  → {label}: draining (up to {int(drain_budget)}s)...")
    return _graceful_restart_via_sigusr1(pid, drain_timeout=drain_budget)


def _resolve_manage_cmd(cache: dict, scope_: str, scope_cmd_: list, svc_name_: str):
    """Resolve the command prefix for manage-units verbs (None ⇒ no privilege path).

    Manage-units verbs on a *system* service trigger a polkit prompt for non-root
    users, which flashes and dies inside our captured 10-15s subprocess. Root → plain
    systemctl; else ``sudo -n`` blanket probe, then a targeted ``reset-failed`` probe
    so a least-privilege sudoers entry scoped to arkos-gateway* qualifies (idempotent
    no-op we run before every privileged restart anyway). On None the caller must SKIP
    the restart (without draining first!). ``--no-ask-password`` prevents polkit hangs.
    """
    if scope_ in cache:
        return cache[scope_]
    cmd = scope_cmd_ + ["--no-ask-password"]
    if _needs_sudo(scope_):
        sudo_cmd = ["sudo", "-n"] + cmd
        try:
            sudo_ok = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=5).returncode == 0
            if not sudo_ok:
                sudo_ok = subprocess.run(
                    sudo_cmd + ["reset-failed", svc_name_], capture_output=True, timeout=5
                ).returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            sudo_ok = False
        cmd = sudo_cmd if sudo_ok else None
    cache[scope_] = cmd
    return cmd


def _restart_one_systemd_gateway_unit(
    svc_name: str, *, scope: str, scope_cmd: list, drain_budget: float, _manage_cmd_cache: dict,
    restarted_services: list, failed_or_stale_units: list,
) -> None:
    """Restart one active systemd gateway/serve unit: graceful SIGUSR1 drain, then forced restart.

    Appends settled names to ``restarted_services`` and failures to ``failed_or_stale_units``.
    """
    check = _systemctl(scope_cmd + ["is-active", svc_name], timeout=5)
    if check.stdout.strip() != "active":
        return

    _manage_cmd = _resolve_manage_cmd(_manage_cmd_cache, scope, scope_cmd, svc_name)

    _main_pid = 0
    if _service_unit_supports_graceful_sigusr1_restart(svc_name):
        try:
            _show = _systemctl(scope_cmd + ["show", svc_name, "--property=MainPID", "--value"], timeout=5)
            _main_pid = int((_show.stdout or "").strip() or 0)
        except (ValueError, subprocess.TimeoutExpired, FileNotFoundError):
            _main_pid = 0

    _graceful_ok = _main_pid > 0 and _drain_or_signal_gateway_for_update(_main_pid, drain_budget, svc_name)

    if _graceful_ok:
        if _manage_cmd is not None:
            _systemctl(_manage_cmd + ["reset-failed", svc_name], timeout=10)
            _systemctl(
                _manage_cmd + ["start", svc_name],
                timeout=_systemd_restart_timeout(scope_cmd, svc_name, start_only=True),
            )
            if _wait_for_service_active(scope_cmd, svc_name, timeout=10.0):
                restarted_services.append(svc_name)
                return
        _restart_sec = _service_restart_sec(scope_cmd, svc_name, default=0.0)
        if _manage_cmd is None and _restart_sec > 5.0:
            print(
                f"  → {svc_name}: waiting for systemd "
                f"auto-restart (~{int(_restart_sec)}s; "
                "no root for an immediate restart)..."
            )
        if _wait_for_service_active(scope_cmd, svc_name, timeout=max(10.0, _restart_sec + 10.0)):
            restarted_services.append(svc_name)
            return
        print(f"  ⚠ {svc_name} drained but didn't relaunch — forcing restart")

    if _manage_cmd is None:
        failed_or_stale_units.append(svc_name)
        print(
            f"  ⚠ {svc_name} is a system service and restarting it needs root.\n"
            f"    Restart it manually to load the new version:\n"
            f"      sudo systemctl restart {svc_name}\n"
            f"    To let `arkos update` restart it automatically, allow\n"
            f"    passwordless sudo for systemctl, or run updates with sudo."
        )
        return

    restart = _systemctl_reset_and_restart(_manage_cmd, svc_name, scope_cmd=scope_cmd)
    if restart.returncode != 0:
        failed_or_stale_units.append(svc_name)
        print(f"  ⚠ Failed to restart {svc_name}: {restart.stderr.strip()}")
        return
    if _wait_for_service_active(scope_cmd, svc_name, timeout=10.0):
        restarted_services.append(svc_name)
        return
    print(f"  ⚠ {svc_name} died after restart, retrying...")
    _systemctl_reset_and_restart(_manage_cmd, svc_name, scope_cmd=scope_cmd)
    if _wait_for_service_active(scope_cmd, svc_name, timeout=10.0):
        restarted_services.append(svc_name)
        print(f"  ✓ {svc_name} recovered on retry")
        return
    failed_or_stale_units.append(svc_name)
    _scope_flag = "--user " if scope == "user" else ""
    _sudo_hint = "sudo " if scope == "system" else ""
    print(
        f"  ✗ {svc_name} failed to stay running after restart.\n"
        f"    Check logs: {_sudo_hint}journalctl {_scope_flag}-u {svc_name} --since '2 min ago'\n"
        f"    Recover manually:\n"
        f"      {_sudo_hint}systemctl {_scope_flag}reset-failed {svc_name}\n"
        f"      {_sudo_hint}systemctl {_scope_flag}restart {svc_name}"
    )


def _restart_systemd_gateway_units(restarted_services, failed_or_stale_units, restarted_scoped_units, drain_budget):
    """Restart every active arkos-gateway*/arkos-serve* systemd unit (user + system).

    Settled units → ``restarted_services`` (bare) and ``restarted_scoped_units``
    (``scope/name``); failures → ``failed_or_stale_units``. Per-unit timeouts isolated.
    """
    from arkos_cli.gateway import supports_systemd_services, _ensure_user_systemd_env
    if not supports_systemd_services():
        return
    _manage_cmd_cache: dict = {}
    with suppress(Exception):
        _ensure_user_systemd_env()

    def _on_list_timeout(scope: str, exc: subprocess.TimeoutExpired) -> None:
        print(
            f"  ⚠ systemctl timed out listing {scope}-scope "
            f"gateway units ({exc.cmd if exc.cmd else 'unknown command'}). "
            f"Check the gateway with: arkos gateway status"
        )

    def _on_unit_timeout(svc_name: str, exc: subprocess.TimeoutExpired) -> None:
        failed_or_stale_units.append(svc_name)
        print(
            f"  ⚠ systemctl timed out restarting {svc_name} "
            f"({exc.cmd if exc.cmd else 'unknown command'}); "
            f"continuing with remaining gateways"
        )

    for scope, scope_cmd, result in _systemd_gateway_unit_listings(_on_list_timeout):
        _scope_mark = len(restarted_services)
        try:
            _for_each_systemd_gateway_unit(
                result.stdout,
                process_unit=lambda svc_name: _restart_one_systemd_gateway_unit(
                    svc_name,
                    scope=scope,
                    scope_cmd=scope_cmd,
                    drain_budget=drain_budget,
                    _manage_cmd_cache=_manage_cmd_cache,
                    restarted_services=restarted_services,
                    failed_or_stale_units=failed_or_stale_units,
                ),
                on_unit_timeout=_on_unit_timeout,
            )
        finally:
            restarted_scoped_units.update(f"{scope}/{name}" for name in restarted_services[_scope_mark:])


@dataclass
class _GatewayRestartOutcome:
    """Restart-phase bookkeeping. ``restarted_services`` keeps bare unit names (fleet
    probe, receipt, summary read it); ``incomplete`` ⇒ a gateway may still be stale."""

    incomplete: bool
    phase_errors: list
    pre_restart_gateway_pids: "list | None"
    restarted_services: list
    failed_or_stale_units: list
    relaunched_profiles: list
    externally_supervised_profiles: list
    killed_pids: set
    stopped_unmapped_pids: set = field(default_factory=set)

    def fleet_probe_signals(self) -> tuple:
        """``(pre_restart_pids, killed_pids)`` with the unmapped stops removed — the signals that
        legitimately predict a fleet-matrix row."""
        pre = self.pre_restart_gateway_pids
        if pre is not None:
            pre = [pid for pid in pre if pid not in self.stopped_unmapped_pids]
        return pre, self.killed_pids - self.stopped_unmapped_pids

    def record_receipt(self, **extra) -> None:
        """Best-effort ``record_gateway_restart`` from the current bookkeeping."""
        with suppress(Exception):
            from arkos_cli.update_receipt import record_gateway_restart
            record_gateway_restart(
                restarted_services=self.restarted_services, relaunched_profiles=self.relaunched_profiles,
                externally_supervised_profiles=self.externally_supervised_profiles,
                killed_pids=sorted(self.killed_pids), failed_units=self.failed_or_stale_units,
                incomplete=self.incomplete, **extra,
            )


def _restart_manual_gateways(out: _GatewayRestartOutcome, _drain_budget) -> None:
    """Drain/stop every manual (non-service) gateway and print the restart summary.

    Mutates ``out`` in place; raises so the caller's abort recovery fires.
    """
    import signal as _signal
    from arkos_cli.gateway import (
        find_gateway_pids, find_profile_gateway_processes, _prepare_profile_gateway_update_restart, _get_service_pids,
        _wait_for_gateway_exit,
    )
    service_pids = _get_service_pids(all_profiles=True)
    manual_pids = find_gateway_pids(exclude_pids=service_pids, all_profiles=True)
    profile_processes = {
        proc.pid: proc
        for proc in find_profile_gateway_processes(exclude_pids=service_pids)
        if proc.pid in manual_pids
    }
    unrestartable_pids = set()
    for pid, proc in profile_processes.items():
        restart_mode = _prepare_profile_gateway_update_restart(proc.profile, pid)
        if restart_mode is None:
            print(
                f"  ⚠ {proc.profile}: could not arm an automatic "
                f"gateway restart for PID {pid} — stopping it instead "
                "so it cannot keep running pre-update code"
            )
            unrestartable_pids.add(pid)
            continue
        if not _drain_or_signal_gateway_for_update(pid, _drain_budget, proc.profile):
            with suppress(ProcessLookupError, PermissionError):
                os.kill(pid, _signal.SIGTERM)
        _wait_for_gateway_exit(timeout=5.0, force_after=None)
        out.killed_pids.add(pid)
        if restart_mode == "external-supervisor":
            out.externally_supervised_profiles.append(proc.profile)
        else:
            out.relaunched_profiles.append(proc.profile)

    for pid in manual_pids:
        if pid in profile_processes and pid not in unrestartable_pids:
            continue
        with suppress(ProcessLookupError, PermissionError):
            os.kill(pid, _signal.SIGTERM)
            out.killed_pids.add(pid)
            out.stopped_unmapped_pids.add(pid)

    if out.restarted_services or out.killed_pids:
        print()
        for svc in out.restarted_services:
            print(f"  ✓ Restarted {svc}")
        if out.relaunched_profiles:
            print(f"  ✓ Restarting manual gateway profile(s): {', '.join(out.relaunched_profiles)}")
        if out.externally_supervised_profiles:
            names = ", ".join(out.externally_supervised_profiles)
            print(f"  ✓ Handed gateway profile(s) back to their external supervisor: {names}")
        unmapped_count = (len(out.killed_pids) - len(out.relaunched_profiles) - len(out.externally_supervised_profiles))
        if unmapped_count:
            print(f"  → Stopped {unmapped_count} manual gateway process(es)")
            print("    Restart manually: arkos gateway run")
            if unmapped_count > 1:
                print("    (or: arkos -p <profile> gateway run  for each profile)")


def _force_kill_stuck_gateways(killed_pids) -> None:
    """Survivor sweep: gateways ignoring SIGTERM (stuck drain, blocked I/O, zombie) never
    exit, so the watcher never respawns and ImportErrors persist. Give graceful paths a
    moment, then SIGKILL remaining pre-update PIDs."""
    with _best_effort('Post-restart survivor sweep failed: %s'):
        from arkos_cli.gateway import find_gateway_pids, _get_service_pids
        _time.sleep(3.0)
        _surviving = find_gateway_pids(exclude_pids=_get_service_pids(all_profiles=True), all_profiles=True)
        _stuck = [pid for pid in _surviving if pid in killed_pids]
        if _stuck:
            print()
            print(f"  ⚠ {len(_stuck)} gateway process(es) ignored SIGTERM — force-killing")
            from gateway.status import get_process_start_time, terminate_pid
            for pid in _stuck:
                with suppress(ProcessLookupError, PermissionError, OSError):
                    terminate_pid(pid, force=True, expected_start_time=get_process_start_time(pid))
            _time.sleep(1.5)


def _recover_after_restart_phase_abort(
    e, _pre_update_plan, out: _GatewayRestartOutcome, *, gateway_mode, restarted_scoped_units
) -> None:
    """Phase-abort recovery: fresh-child restart + fail-closed verdict; updates ``out`` in place."""
    from arkos_cli.update_cmd import (
        _abort_recovery_is_complete, _recover_gateway_restart_after_abort, _surviving_pre_update_serve_runtimes,
        _warn_stale_serve_runtimes, _write_gateway_update_exit_code,
    )
    logger.debug("Gateway restart during update failed: %s", e)
    out.phase_errors.append(str(e))
    _surviving = _surviving_gateway_pids_after_failed_restart()
    _planned_gateway_profiles = {
        runtime.profile
        for runtime in getattr(_pre_update_plan, "runtimes", ()) or ()
        if getattr(runtime, "kind", None) == "gateway"
        and isinstance(getattr(runtime, "profile", None), str)
    }
    _already_restarted_profiles = set(out.relaunched_profiles) | set(out.externally_supervised_profiles)
    _already_restarted_profiles.update(
        profile
        for profile in _planned_gateway_profiles
        if any(_gateway_service_matches_profile(profile, service) for service in out.restarted_services)
    )
    _recovery_result = _recover_gateway_restart_after_abort(
        _pre_update_plan, gateway_mode=gateway_mode, skip_profiles=_already_restarted_profiles,
        skip_units=set(restarted_scoped_units),
    )
    _serve_units_failed = list((_recovery_result.get("serve_units") or {}).get("failed") or [])
    _stale_runtime_rows = _surviving_pre_update_serve_runtimes(_pre_update_plan)
    _recovery_result["stale_runtimes"] = _stale_runtime_rows
    _recovery_verified = set(_recovery_result.get("verified") or [])
    out.relaunched_profiles.extend(
        profile for profile in sorted(_recovery_verified) if profile not in out.relaunched_profiles
    )
    if _abort_recovery_is_complete(
        planned_gateway_profiles=_planned_gateway_profiles,
        covered_gateway_profiles=_already_restarted_profiles | _recovery_verified,
        recovery_result=_recovery_result,
        stale_runtime_rows=_stale_runtime_rows,
    ):
        out.incomplete = False
    elif (
        _restart_phase_failure_is_incomplete(_surviving, out.pre_restart_gateway_pids)
        or _stale_runtime_rows
        or _serve_units_failed
    ):
        out.incomplete = True
        _warn_gateway_restart_phase_aborted(e, _surviving)
        _warn_stale_serve_runtimes(_stale_runtime_rows)
        if gateway_mode:
            _write_gateway_update_exit_code(False)
    out.record_receipt(phase_error=str(e), fresh_recovery=_recovery_result)


def _restart_gateway_fleet_after_update(_pre_update_plan, gateway_mode: bool):
    """Restart every running gateway (systemd, launchd, manual) onto the pulled code.

    Never raises: a phase abort runs fresh-child recovery and fails closed unless
    every planned gateway is verifiably covered.
    """
    from arkos_cli.update_cmd import _m, _write_gateway_update_exit_code
    out = _GatewayRestartOutcome(
        incomplete=False, phase_errors=[], pre_restart_gateway_pids=[], restarted_services=[], failed_or_stale_units=[],
        relaunched_profiles=[], externally_supervised_profiles=[], killed_pids=set(),
    )
    restarted_scoped_units: set = set()

    _m()._purge_stale_arkos_modules()
    try:
        from arkos_cli.gateway import (  # noqa: F401
            is_macos,
            find_gateway_pids,
            find_profile_gateway_processes,
            _prepare_profile_gateway_update_restart,
            _get_service_pids,
            _wait_for_gateway_exit,
        )
        try:
            from arkos_cli.gateway import _get_restart_exit_wait_budget
            _drain_budget = max(float(_get_restart_exit_wait_budget()), 45.0)
        except Exception:
            _drain_budget = 45.0

        try:
            out.pre_restart_gateway_pids = list(find_gateway_pids(all_profiles=True))
        except Exception:
            out.pre_restart_gateway_pids = None

        _restart_systemd_gateway_units(
            out.restarted_services, out.failed_or_stale_units, restarted_scoped_units, _drain_budget
        )

        if is_macos():
            with suppress(FileNotFoundError, ImportError):
                _restart_macos_launchd_gateways(out.restarted_services, out.failed_or_stale_units, _drain_budget)

        _restart_manual_gateways(out, _drain_budget)

        if out.failed_or_stale_units:
            out.incomplete = True
            if gateway_mode:
                _write_gateway_update_exit_code(False)
        _warn_incomplete_gateway_fleet_restart(out.failed_or_stale_units)
        out.record_receipt()
        _force_kill_stuck_gateways(out.killed_pids)

    except Exception as e:
        _recover_after_restart_phase_abort(
            e, _pre_update_plan, out, gateway_mode=gateway_mode, restarted_scoped_units=restarted_scoped_units
        )

    return out


def _print_legacy_units_warning() -> None:
    """Legacy arkos.service fights arkos-gateway.service over the bot token; warn on
    every update until migrated."""
    from arkos_cli.gateway import (has_legacy_arkos_units, _find_legacy_arkos_units, supports_systemd_services)
    if not (supports_systemd_services() and has_legacy_arkos_units()):
        return
    print()
    print("⚠ Legacy Arkos gateway unit(s) detected:")
    for name, path, is_sys in _find_legacy_arkos_units():
        scope = "system" if is_sys else "user"
        print(f"    {path}  ({scope} scope)")
    print()
    print("  These pre-rename units (arkos.service) fight the current")
    print("  arkos-gateway.service for the bot token and cause SIGTERM")
    print("  flap loops. Remove them with:")
    print()
    print("    arkos gateway migrate-legacy")
    print()
    print("  (add `sudo` if any are in system scope)")


def _collect_fleet_snapshot(restart, rows_expected: bool) -> list:
    """Fleet version rows, polled over a bounded settle window when runtimes are expected.

    Gateways need time to rewrite gateway_state.json; Windows resumes DETACHED (~10s boot),
    so a single 2s sleep reported "no rows" on healthy resumes. A "down" row may be a
    detached replacement still booting: poll until none remain or the deadline passes.
    Pre-restart PIDs make a gateway stopped WITHOUT verified replacement a DOWN row (exit 1)
    instead of no row at all.
    """
    from arkos_cli.update_receipt import collect_fleet_versions
    if not rows_expected:
        return collect_fleet_versions(pre_restart_pids=restart.pre_restart_gateway_pids)
    _fleet_deadline = _time.monotonic() + 30.0
    while True:
        _time.sleep(2.0)
        snapshot = collect_fleet_versions(pre_restart_pids=restart.pre_restart_gateway_pids)
        if snapshot and not any(row.get("state") == "down" for row in snapshot):
            return snapshot
        if _time.monotonic() >= _fleet_deadline:
            return snapshot


def _verify_fleet_after_update(restart, *, _pre_update_plan, _windows_gateway_resume, node_failures, update_complete):
    """Post-restart verification: legacy-unit warning, dashboard cleanup, stale serve
    probe, fleet version matrix, plan-vs-execution reconciliation, receipt finalize.

    Exits 1 (leaving ``fleet_restart_pending`` for the next catch-up) when any gateway
    may still be stale; otherwise clears the marker.
    """
    from arkos_cli.update_cmd import (
        _finish_dashboard_update_cleanup, _m, _surviving_pre_update_serve_runtimes, _warn_stale_serve_runtimes,
    )
    with _best_effort('Legacy unit check during update failed: %s'):
        _print_legacy_units_warning()

    _finish_dashboard_update_cleanup(node_failures, already_restarted_units=set(restart.restarted_services))

    _stale_serve_rows: "list | None" = None
    with _best_effort('Failed to check for surviving serve runtimes: %s'):
        _stale_serve_rows = _surviving_pre_update_serve_runtimes(_pre_update_plan)
        if _stale_serve_rows:
            _warn_stale_serve_runtimes(_stale_serve_rows)

    print()
    print("Tip: You can now select a provider and model:")
    print("  arkos model              # Select provider and model")

    _fleet_snapshot: list = []
    with _best_effort('Fleet version verification failed: %s'):
        from arkos_cli.update_receipt import print_fleet_version_matrix
        _pre_restart, _killed = restart.fleet_probe_signals()
        _fleet_rows_expected = _m()._fleet_probe_expected_runtimes(
            _pre_update_plan, _pre_restart, _windows_gateway_resume, restart.restarted_services, _killed,
        )
        _fleet_snapshot = _collect_fleet_snapshot(restart, _fleet_rows_expected)
        if print_fleet_version_matrix(_fleet_snapshot):
            restart.incomplete = True
        elif not _fleet_snapshot and _fleet_rows_expected:
            print(
                "\n⚠ Fleet version check returned no rows even though"
                " gateway runtimes were expected — verification incomplete."
            )
            restart.incomplete = True

    with _best_effort('Runtime-outcome reconciliation failed: %s'):
        if _pre_update_plan is not None and _pre_update_plan.runtimes:
            from arkos_cli.update_inventory import (match_runtime_outcomes, report_unaccounted_runtimes)
            _runtime_outcomes = match_runtime_outcomes(
                _pre_update_plan,
                restarted_services=restart.restarted_services,
                relaunched_profiles=restart.relaunched_profiles,
                externally_supervised_profiles=restart.externally_supervised_profiles,
                killed_pids=restart.killed_pids,
                failed_units=restart.failed_or_stale_units,
                stale_serve_pids=(
                    {row.get("pid") for row in _stale_serve_rows}
                    if _stale_serve_rows is not None
                    else None
                ),
            )
            if report_unaccounted_runtimes(_runtime_outcomes):
                restart.incomplete = True
            with suppress(Exception):
                import arkos_cli.update_receipt as _ur
                if _ur._current is not None:
                    _ur._current.data["runtime_outcomes"] = _runtime_outcomes

    with _best_effort('Update receipt finalize failed: %s'):
        from arkos_cli.update_receipt import finalize_update_receipt
        _receipt_path = finalize_update_receipt(
            "partial" if restart.incomplete or not update_complete else "success",
            fleet=_fleet_snapshot,
        )
        if _receipt_path is not None:
            logger.info("Update receipt written: %s", _receipt_path)

    if restart.incomplete:
        sys.exit(1)
    _clear_fleet_restart_pending_marker()


def _restart_phase_failure_is_incomplete(surviving, pre_restart_pids) -> bool:
    """Whether an escaped restart-phase exception must fail the update.

    Fail closed unless provably safe: ``surviving`` None (unprobeable) or non-empty →
    stale. ``[]`` proves safety ONLY if nothing ran beforehand; a pre-restart gateway
    (``pre_restart_pids`` non-empty or None) now gone was stopped unverified.

    * ``surviving is None`` — the survivor probe could not determine state (typically the freshly-pulled
    ``arkos_cli.gateway`` no longer imports, one of the ways the phase aborts). That is proof-of-safety
    ONLY when nothing was running before we touched anything. If a gateway was discovered pre-restart
    (``pre_restart_pids`` non-empty, or ``None`` meaning the pre-state could not be read), it was stopped
    without a verified replacement, so we still fail closed.
    """
    if surviving is None or surviving:
        return True
    return pre_restart_pids is None or bool(pre_restart_pids)


def _fleet_probe_expected_runtimes(
    pre_update_plan, pre_restart_pids, windows_resume_token, restarted_services, killed_pids,
) -> bool:
    """Whether the post-update fleet probe should have produced rows.

    ``collect_fleet_versions`` swallows every failure and an empty matrix prints as
    healthy, so zero rows is only proof-of-safety when NOTHING says a gateway existed
    pre-update. Signals: ``restarted_services``/``killed_pids``; ``pre_restart_pids``
    non-empty or None (same contract as ``_restart_phase_failure_is_incomplete``); plan
    inventoried ≥1 ``kind == "gateway"`` runtime. ``windows_resume_token`` is deliberately EXCLUDED: it is
    pause/resume bookkeeping, not an inventory, and its entries don't map to probe rows
    (``unmapped`` Scheduled-Task gateways never publish gateway_state.json; a paused
    profile resumes DETACHED). Counting it made every Windows update that paused a
    gateway exit 1 after a long silent wait; a live pre-update Windows gateway is already
    covered by ``pre_restart_pids`` and the plan. The same condition gates the settle sleep....
    """
    del windows_resume_token
    if restarted_services or killed_pids:
        return True
    if pre_restart_pids is None or pre_restart_pids:
        return True
    with suppress(Exception):
        if pre_update_plan is not None and any(
            getattr(runtime, "kind", None) == "gateway" for runtime in pre_update_plan.runtimes
        ):
            return True
    return False


def _wait_for_service_active(scope_cmd_: list, svc_name_: str, timeout: float = 10.0) -> bool:
    """Poll ``systemctl is-active`` (0.5s) up to ``timeout``: the Stopped -> Started
    transition isn't instantaneous, so a one-shot check falsely reports down."""
    deadline = _time.monotonic() + max(timeout, 0.5)
    while True:
        with suppress(FileNotFoundError, subprocess.TimeoutExpired):
            _verify = _systemctl(scope_cmd_ + ["is-active", svc_name_], timeout=5)
            if _verify.stdout.strip() == "active":
                return True
        if _time.monotonic() >= deadline:
            return False
        _time.sleep(0.5)


_RESTART_SEC_UNITS = (("ms", 0.001), ("us", 0.000001), ("min", 60.0), ("s", 1.0))


def _service_restart_sec(scope_cmd_: list, svc_name_: str, default: float = 0.0) -> float:
    """Read the unit's ``RestartUSec`` in seconds. ``is-active`` pollers must wait
    >= RestartSec + slack or they give up *during* the cooldown and misreport."""
    try:
        _show = _systemctl(scope_cmd_ + ["show", svc_name_, "--property=RestartUSec", "--value"], timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return default
    raw = (_show.stdout or "").strip()
    if not raw or raw == "infinity":
        return default
    total = 0.0
    matched = False
    for part in raw.split():
        for _suf, _mult in _RESTART_SEC_UNITS:
            if part.endswith(_suf):
                with suppress(ValueError):
                    total += float(part[: -len(_suf)]) * _mult
                    matched = True
                break
    return total if matched else default
