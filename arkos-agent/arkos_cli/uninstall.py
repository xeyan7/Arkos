"""Arkos Uninstaller."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from arkos_constants import get_arkos_home

from arkos_cli.colors import Colors, color

def _logger(mark: str, col: str):
    return lambda msg: print(f"{color(mark, col)} {msg}")


log_info = _logger("→", Colors.CYAN)
log_success = _logger("✓", Colors.GREEN)
log_warn = _logger("⚠", Colors.YELLOW)


def _print_box(middle: str, col: str) -> None:
    """Print the 3-line framed heading used by the uninstall screens."""
    print(color("┌─────────────────────────────────────────────────────────┐", col, Colors.BOLD))
    print(color(middle, col, Colors.BOLD))
    print(color("└─────────────────────────────────────────────────────────┘", col, Colors.BOLD))


def _prompt(text: str):
    """``input(text).strip().lower()``; None (after printing "Cancelled.") on Ctrl-C/EOF."""
    try:
        return input(text).strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        print("Cancelled.")
        return None


def _cancelled() -> None:
    print()
    print("Uninstall cancelled.")


def _confirm_yes(text: str) -> bool:
    """Ask the user to type ``yes``; False (after the cancel line, unless Ctrl-C/EOF) otherwise."""
    confirm = _prompt(f"Type '{color('yes', Colors.YELLOW)}' {text}: ")
    if confirm != "yes" and confirm is not None:
        _cancelled()
    return confirm == "yes"


def _remove_each(candidates, remove) -> list:
    """Run ``remove(path)`` per candidate, collecting the ones it reports removed; failures become
    the shared ``Could not remove <path>: <err>`` warning."""
    removed = []
    for path in candidates:
        try:
            if remove(path):
                removed.append(path)
        except Exception as e:
            log_warn(f"Could not remove {path}: {e}")
    return removed


def get_project_root() -> Path:
    """Get the project installation directory."""
    return Path(__file__).parent.parent.resolve()


_SHELL_RC_NAMES = (".bashrc", ".bash_profile", ".profile", ".zshrc", ".zprofile")


def _strip_arkos_path_lines(content: str) -> str:
    """Drop the ``# Arkos`` marker (+ its PATH line) and any arkos PATH line; squash blank runs."""
    new_lines = []
    skip_next = False
    for line in content.split('\n'):
        if '# Arkos' in line or '# arkos-agent' in line:
            skip_next = True
            continue
        if skip_next and ("arkos" in line.lower() and 'PATH' in line):
            skip_next = False
            continue
        skip_next = False
        if "arkos" in line.lower() and ('PATH=' in line or 'path=' in line.lower()):
            continue
        new_lines.append(line)
    new_content = '\n'.join(new_lines)
    while '\n\n\n' in new_content:
        new_content = new_content.replace('\n\n\n', '\n\n')
    return new_content


def remove_path_from_shell_configs():
    """Remove Arkos PATH entries from shell configuration files."""
    removed_from = []
    for config_path in (c for c in (Path.home() / n for n in _SHELL_RC_NAMES) if c.exists()):
        try:
            content = config_path.read_text(encoding="utf-8")
            new_content = _strip_arkos_path_lines(content)
            if new_content != content:
                from utils import atomic_write_text
                atomic_write_text(config_path, new_content, preserve_mode=True)
                removed_from.append(config_path)
        except Exception as e:
            log_warn(f"Could not update {config_path}: {e}")
    return removed_from


def remove_wrapper_script():
    """Remove the arkos wrapper script if it exists."""
    def _unlink_ours(wrapper: Path) -> bool:
        content = wrapper.read_text(encoding="utf-8")
        return _unlink_if('arkos_cli' in content or 'arkos-agent' in content or 'arkos-agent' in content, wrapper)

    candidates = (
        bin_dir / name
        for bin_dir in (Path.home() / ".local" / "bin", Path("/usr/local/bin"))
        for name in ("arkos", "arkos-acp", "arkos-agent", "arkos", "arkos-acp", "arkos-agent"))
    return _remove_each((w for w in candidates if w.exists()), _unlink_ours)


def _unlink_if(ours: bool, path: Path) -> bool:
    """Unlink *path* when it is ours; returns whether it was removed."""
    if ours:
        path.unlink()
    return ours


def _node_symlink_candidate_dirs() -> "list[Path]":
    """Directories where the installer may have placed node/npm/npx symlinks."""
    dirs: list[Path] = [Path.home() / ".local" / "bin"]
    if sys.platform == "linux":
        dirs.append(Path("/usr/local/bin"))
    prefix = os.environ.get("PREFIX", "")
    if "com.termux" in prefix:
        dirs.append(Path(prefix) / "bin")
    return dirs


def remove_node_symlinks(arkos_home: Path) -> list:
    """Remove the node/npm/npx symlinks the installer placed on PATH. Every candidate dir is
    checked (``/usr/local/bin`` root FHS, ``$PREFIX/bin`` Termux, ``~/.local/bin`` otherwise / older
    installs) so uninstall works regardless of how the install was done."""
    node_dir = (arkos_home / "node").resolve()

    def _unlink_ours(link: Path) -> bool:
        if not link.is_symlink():
            return False
        target = (link.parent / os.readlink(link)).resolve()
        return _unlink_if(target == node_dir or node_dir in target.parents, link)

    candidates = (bin_dir / name for name in ("node", "npm", "npx") for bin_dir in _node_symlink_candidate_dirs())
    return _remove_each(candidates, _unlink_ours)


def uninstall_gateway_service():
    """Kill standalone gateways, then remove the per-platform service (systemd user+system /
    launchd / Scheduled Task + Startup folder). Termux/Android has neither: only the kill applies."""
    import platform
    stopped_something = False
    try:
        from arkos_cli.gateway import kill_gateway_processes, find_gateway_pids
        killed = kill_gateway_processes() if find_gateway_pids() else 0
        if killed:
            log_success(f"Killed {killed} running gateway process(es)")
            stopped_something = True
    except Exception as e:
        log_warn(f"Could not check for gateway processes: {e}")

    if os.getenv("TERMUX_VERSION") or "com.termux/files/usr" in os.getenv("PREFIX", ""):
        return stopped_something

    remover, warn_label = _GATEWAY_SERVICE_REMOVERS.get(platform.system(), (None, ""))
    if remover is not None:
        try:
            stopped_something = remover() or stopped_something
        except Exception as e:
            log_warn(f"{warn_label}: {e}")
    return stopped_something


def _remove_systemd_gateway() -> bool:
    """Linux: uninstall systemd services (both user and system scopes)."""
    from arkos_cli.gateway import _systemctl_cmd, get_service_name, get_systemd_unit_path
    svc_name = get_service_name()
    removed_any = False
    for is_system, scope in ((False, "user"), (True, "system")):
        unit_path = get_systemd_unit_path(system=is_system)
        if not unit_path.exists():
            continue
        try:
            if is_system and os.geteuid() != 0:
                log_warn(f"System gateway service exists at {unit_path} but needs sudo to remove")
                continue
            cmd = _systemctl_cmd(is_system)
            for verb in ("stop", "disable"):
                subprocess.run(cmd + [verb, svc_name], capture_output=True, check=False)
            unit_path.unlink()
            subprocess.run(cmd + ["daemon-reload"], capture_output=True, check=False)
            log_success(f"Removed {scope} gateway service ({unit_path})")
            removed_any = True
        except Exception as e:
            log_warn(f"Could not remove {scope} gateway service: {e}")
    return removed_any


def _remove_launchd_gateway() -> bool:
    """macOS: uninstall launchd plist."""
    from arkos_cli.gateway import get_launchd_plist_path
    plist_path = get_launchd_plist_path()
    if not plist_path.exists():
        return False
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, check=False)
    plist_path.unlink()
    log_success(f"Removed macOS gateway service ({plist_path})")
    return True


def _remove_windows_gateway() -> bool:
    """Windows: uninstall Scheduled Task + Startup-folder entry via ``gateway_windows`` (it owns
    schtasks /Delete, the .cmd unlink and stopping the detached pythonw gateway)."""
    from arkos_cli import gateway_windows as gw
    if not any(probe() for probe in (gw.is_installed, gw.is_task_registered, gw.is_startup_entry_installed)):
        return False
    try:
        gw.stop()
    except Exception as e:
        log_warn(f"Could not stop Windows gateway cleanly: {e}")
    try:
        gw.uninstall()
        log_success("Removed Windows gateway (Scheduled Task + Startup entry)")
        return True
    except Exception as e:
        log_warn(f"Could not fully uninstall Windows gateway: {e}")
        return False


_GATEWAY_SERVICE_REMOVERS = {
    "Linux": (_remove_systemd_gateway, "Could not check systemd gateway services"),
    "Darwin": (_remove_launchd_gateway, "Could not remove launchd gateway service"),
    "Windows": (_remove_windows_gateway, "Could not check Windows gateway service")}



def _arkos_path_markers(arkos_home: Path, *, include_managed_bin: bool = False) -> list[str]:
    r"""Prefixes identifying Arkos-owned User-PATH entries (prefix match sweeps git\cmd, git\bin,
    node...). ``include_managed_bin`` adds ``<root>\bin`` (launchers + managed uv) — only when that
    dir is about to be deleted, so a keep-data uninstall keeps the working uv resolvable."""
    root = str(arkos_home).rstrip("\\/")
    subs = ("arkos-agent", "git", "node", "venv") + (("bin",) if include_managed_bin else ())
    return [f"{root}\\{sub}" for sub in subs]


def remove_path_from_windows_registry(arkos_home: Path, *, include_managed_bin: bool = False) -> list[str]:
    """Strip Arkos-owned entries from User-scope PATH in the registry (see ``_arkos_path_markers``)."""
    markers = tuple(m.lower() for m in _arkos_path_markers(arkos_home, include_managed_bin=include_managed_bin))

    def edit(winreg, key, removed):
        try:
            path_value, path_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            return
        kept: list[str] = []
        for entry in (e for e in path_value.split(";") if e):
            is_ours = entry.rstrip("\\/").lower().startswith(markers)
            (removed if is_ours else kept).append(entry)
        if removed:
            winreg.SetValueEx(key, "Path", 0, path_type, ";".join(kept))

    return _edit_user_environment(edit, warn_label="Could not edit User PATH in registry")


def remove_arkos_env_vars_windows() -> list[str]:
    """Delete ARKOS_HOME and ARKOS_GIT_BASH_PATH from User-scope env vars."""
    def edit(winreg, key, removed):
        for name in ("ARKOS_HOME", "ARKOS_GIT_BASH_PATH"):
            try:
                winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                continue
            try:
                winreg.DeleteValue(key, name)
                removed.append(name)
            except OSError as e:
                log_warn(f"Could not delete {name} from User env: {e}")

    return _edit_user_environment(edit, warn_label="Could not open User Environment key")


def _edit_user_environment(edit, *, warn_label: str) -> list[str]:
    """Open HKCU\\Environment read/write and run ``edit(winreg, key, removed)``. Returns what
    ``edit`` appended to ``removed`` even if a later registry call raised (callers report exactly
    what was touched); ``[]`` off-Windows (no ``winreg``)."""
    removed: list[str] = []
    try:
        import winreg
    except ImportError:
        return removed
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                            winreg.KEY_READ | winreg.KEY_WRITE) as key:
            edit(winreg, key, removed)
    except OSError as e:
        log_warn(f"{warn_label}: {e}")
    return removed


def remove_portable_tooling_windows(arkos_home: Path) -> list[Path]:
    """Delete the PortableGit / Node / gateway-service dirs the Windows installer created under
    ``arkos_home`` (isolated from any system Git / Node, so nothing else breaks)."""
    targets = (arkos_home / sub for sub in ("git", "node", "gateway-service"))
    return _remove_each((t for t in targets if t.exists()), lambda t: shutil.rmtree(t) or True)


def remove_windows_bin_launchers(*, windows: bool | None = None) -> list[Path]:
    """Delete the ``arkos`` launchers install.ps1 staged in the managed ``bin`` dir: every mode
    deletes the checkout, so a launcher pointing at ``<checkout>/venv`` would dangle (worse than
    command-not-found); the managed uv stays for keep-data reinstalls. Our own running trampoline is
    locked against deletion but not rename, so it is renamed aside with a non-executable suffix."""
    if not (_is_windows() if windows is None else windows):
        return []
    try:
        from arkos_cli._install_repair import _WINDOWS_BIN_LAUNCHERS
        from arkos_constants import get_default_arkos_root
        bin_dir = get_default_arkos_root() / "bin"
    except Exception as e:
        log_warn(f"Could not locate the managed binary dir: {e}")
        return []

    def _unlink_or_rename_aside(launcher: Path) -> bool:
        try:
            launcher.unlink()
        except OSError:
            os.rename(launcher, launcher.with_name(f"{launcher.name}.uninstalled.{os.getpid()}"))
        return True

    candidates = (bin_dir / f"{name}{suffix}" for name in _WINDOWS_BIN_LAUNCHERS for suffix in (".exe", ".cmd"))
    return _remove_each((p for p in candidates if p.exists()), _unlink_or_rename_aside)


def _is_windows() -> bool:
    return sys.platform == "win32"


def _is_default_arkos_home(arkos_home: Path) -> bool:
    """Return True when ``arkos_home`` points at the default (non-profile) root."""
    try:
        from arkos_constants import get_default_arkos_root
        return arkos_home.resolve() == get_default_arkos_root().resolve()
    except Exception:
        return False


def _discover_named_profiles():
    """``ProfileInfo`` for every non-default profile; ``[]`` when profile support is unavailable."""
    try:
        from arkos_cli.profiles import list_profiles
    except Exception:
        return []
    try:
        return [p for p in list_profiles() if not getattr(p, "is_default", False)]
    except Exception as e:
        log_warn(f"Could not enumerate profiles: {e}")
        return []


def _uninstall_profile(profile) -> None:
    """Fully uninstall a named profile: stop its gateway, remove its alias, wipe its home. Shells
    out to ``arkos -p <name> gateway stop|uninstall`` because service names / unit paths derive
    from the current ARKOS_HOME and can't be switched in-process."""
    name = profile.name
    log_info(f"Uninstalling profile '{name}'...")

    arkos_invocation = [sys.executable, "-m", "arkos_cli.main", "--profile", name]
    for subcmd in ("stop", "uninstall"):
        try:
            subprocess.run(
                arkos_invocation + ["gateway", subcmd], capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=60, check=False)
        except subprocess.TimeoutExpired:
            log_warn(f"  Gateway {subcmd} timed out for '{name}'")
        except Exception as e:
            log_warn(f"  Could not run gateway {subcmd} for '{name}': {e}")

    alias_path = getattr(profile, "alias_path", None)
    if alias_path and alias_path.exists():
        try:
            alias_path.unlink()
            log_success(f"  Removed alias {alias_path}")
        except Exception as e:
            log_warn(f"  Could not remove alias {alias_path}: {e}")
    _rmtree_step(profile.path, indent="  ", fully=False)


def run_gui_uninstall(args):
    """``arkos uninstall --gui``: remove the desktop app's built artifacts, packaged bundle
    (best-effort) and Electron userData — never config/sessions/.env, the agent or its venv."""
    from arkos_cli.gui_uninstall import agent_is_installed, gui_install_summary, uninstall_gui
    arkos_home = get_arkos_home()
    summary = gui_install_summary(arkos_home)
    skip_confirm = bool(getattr(args, "yes", False))

    print()
    _print_box("│         ⚕ Arkos Chat GUI Uninstaller                  │", Colors.MAGENTA)
    print()

    if not summary["gui_installed"]:
        print("No Arkos Chat GUI installation was found.")
        print(f"  Checked: {arkos_home}, and the standard app locations for this OS.")
        return

    print(color("This removes the Chat GUI only. The Arkos agent stays installed.", Colors.CYAN))
    print()
    print(color("Will remove:", Colors.YELLOW, Colors.BOLD))
    for p in (*summary["source_built_artifacts"], *summary["packaged_app_paths"]):
        print(f"  • {p}")
    if summary["userdata_exists"]:
        print(f"  • {summary['userdata_dir']}  (desktop app data)")
    print()
    if agent_is_installed(arkos_home):
        print(color("Kept intact:", Colors.GREEN, Colors.BOLD))
        print(f"  • The Arkos agent at {arkos_home / 'arkos-agent'}")
        print(f"  • Your config, sessions, and secrets under {arkos_home}")
        print()

    if not skip_confirm and not _confirm_yes("to remove the Chat GUI"):
        return

    print()
    print(color("Uninstalling Chat GUI...", Colors.CYAN, Colors.BOLD))
    print()
    uninstall_gui(arkos_home)

    print()
    _print_box("│            ✓ Chat GUI Uninstalled!                      │", Colors.GREEN)
    print()
    print("The Arkos agent is still installed. Run 'arkos' to use the CLI,")
    print("or 'arkos uninstall' to remove the agent too.")
    print()


def run_uninstall(args):
    """Interactive/``--yes`` uninstall: full removes code and ``~/.arkos/``; keep-data removes only
    the code so configs, data and logs survive a reinstall."""
    project_root = get_project_root()
    arkos_home = get_arkos_home()

    full_flag = bool(getattr(args, "full", False))
    if bool(getattr(args, "dry_run", False)):
        _print_uninstall_dry_run(
            project_root=project_root, arkos_home=arkos_home, full_uninstall=full_flag)
        return

    is_default_profile = _is_default_arkos_home(arkos_home)
    named_profiles = _discover_named_profiles() if is_default_profile else []

    if bool(getattr(args, "yes", False)):
        _perform_uninstall(
            project_root=project_root, arkos_home=arkos_home, full_uninstall=full_flag,
            remove_profiles=False, named_profiles=named_profiles)
        return

    print()
    _print_box("│            ⚕ Arkos Uninstaller                  │", Colors.MAGENTA)
    print()

    print(color("Current Installation:", Colors.CYAN, Colors.BOLD))
    print(f"  Code:    {project_root}")
    print(f"  Config:  {arkos_home / 'config.yaml'}")
    print(f"  Secrets: {arkos_home / '.env'}")
    print(f"  Data:    {arkos_home / 'cron/'}, {arkos_home / 'sessions/'}, {arkos_home / 'logs/'}")
    print()

    if named_profiles:
        print(color("Other profiles detected:", Colors.CYAN, Colors.BOLD))
        for p in named_profiles:
            print(f"  • {p.name}{' (gateway running)' if getattr(p, 'gateway_running', False) else ''}: {p.path}")
        print()

    print(color("Uninstall Options:", Colors.YELLOW, Colors.BOLD))
    print()
    print("  1) " + color("Keep data", Colors.GREEN) + " - Remove code only, keep configs/sessions/logs")
    print("     (Recommended - you can reinstall later with your settings intact)")
    print()
    print("  2) " + color("Full uninstall", Colors.RED) + " - Remove everything including all data")
    print("     (Warning: This deletes all configs, sessions, and logs permanently)")
    print()
    print("  3) " + color("Cancel", Colors.CYAN) + " - Don't uninstall")
    print()

    choice = _prompt(color("Select option [1/2/3]: ", Colors.BOLD))
    if choice is None:
        return

    if choice in {"3", "c", "cancel", "q", "quit", "n", "no"}:
        _cancelled()
        return

    full_uninstall = (choice == "2")

    remove_profiles = False
    n_profiles = len(named_profiles)
    profile_names = ", ".join(p.name for p in named_profiles)
    if full_uninstall and named_profiles:
        print()
        print(color("Other profiles will NOT be removed by default.", Colors.YELLOW))
        print(f"Found {n_profiles} named profile(s): {profile_names}")
        print()
        resp = _prompt(color(f"Also stop and remove these {n_profiles} profile(s)? [y/N]: ", Colors.BOLD))
        if resp is None:
            return
        remove_profiles = resp in {"y", "yes"}

    print()
    if full_uninstall:
        print(color("⚠️  WARNING: This will permanently delete ALL Arkos data!", Colors.RED, Colors.BOLD))
        print(color("   Including: configs, API keys, sessions, scheduled jobs, logs", Colors.RED))
        if remove_profiles:
            print(color(f"   Plus {n_profiles} profile(s): {profile_names}", Colors.RED))
    else:
        print("This will remove the Arkos code but keep your configuration and data.")

    print()
    if not _confirm_yes("to confirm"):
        return

    _perform_uninstall(
        project_root=project_root, arkos_home=arkos_home, full_uninstall=full_uninstall,
        remove_profiles=remove_profiles, named_profiles=named_profiles)


def _print_uninstall_dry_run(*, project_root: Path, arkos_home: Path, full_uninstall: bool) -> None:
    """Print the uninstall plan without stopping services or deleting files."""
    print()
    print(color("Dry run: no files, services, or environment entries will be changed.", Colors.CYAN, Colors.BOLD))
    print()
    print(color("Would inspect/remove:", Colors.YELLOW, Colors.BOLD))
    print("  • Gateway services and standalone gateway processes")
    print("  • Arkos PATH entries from shell configs / Windows User PATH")
    print("  • Arkos wrapper scripts and Arkos-managed node/npm/npx symlinks")
    print("  • Desktop Chat GUI artifacts")
    print(f"  • Code checkout: {project_root}")
    if not full_uninstall:
        print(f"  • Keep Arkos config/data: {arkos_home}")
    else:
        print(f"  • Arkos config/data: {arkos_home}")
        profiles = _discover_named_profiles() if _is_default_arkos_home(arkos_home) else []
        if profiles:
            print("  • Named profiles (interactive uninstall asks before removing):")
            for prof in profiles:
                print(f"    - {prof.name}: {prof.path}")
    print()


def _remove_step(label: str, remove, success_fmt: str, none_msg: str) -> None:
    """Announce ``label``, run ``remove()``, log one success line per removed item (or ``none_msg``)."""
    log_info(label)
    removed = remove()
    for item in removed:
        log_success(success_fmt.format(item))
    if not removed:
        log_info(none_msg)


def _rmtree_step(path: Path, *, indent: str = "", fully: bool = True) -> None:
    """Best-effort ``rmtree`` with the shared success/warning lines."""
    try:
        if path.exists():
            shutil.rmtree(path)
            log_success(f"{indent}Removed {path}")
    except Exception as e:
        log_warn(f"{indent}Could not {'fully ' if fully else ''}remove {path}: {e}")
        if fully:
            log_info("You may need to manually remove it")


def _perform_uninstall(
    *,
    project_root: Path,
    arkos_home: Path,
    full_uninstall: bool,
    remove_profiles: bool,
    named_profiles: list) -> None:
    """The uninstall steps shared by the interactive and ``--yes`` paths: stop gateway -> strip PATH
    (rc files + Windows registry) -> wrapper/launchers/node symlinks -> Chat GUI artifacts -> delete
    the checkout -> (Windows) PortableGit/Node -> optionally ``$ARKOS_HOME`` and named profiles."""
    print()
    print(color("Uninstalling...", Colors.CYAN, Colors.BOLD))
    print()
    log_info("Checking for running gateway...")
    if not uninstall_gateway_service():
        log_info("No gateway service or processes found")

    windows = _is_windows()
    sweep_managed_bin = windows and full_uninstall and _is_default_arkos_home(arkos_home)
    for on_this_platform, label, remove, success_fmt, none_msg in (
        (True, "Removing PATH entries from shell configs...",
         remove_path_from_shell_configs, "Updated {}", "No PATH entries found to remove in shell rc files"),
        (windows, "Removing PATH entries from Windows User environment...",
         lambda: remove_path_from_windows_registry(
             Path(os.path.expandvars(str(arkos_home))), include_managed_bin=sweep_managed_bin),
         "Removed from User PATH: {}", "No Arkos-owned PATH entries in User environment"),
        (windows, "Removing ARKOS_HOME / ARKOS_GIT_BASH_PATH User env vars...",
         remove_arkos_env_vars_windows, "Removed User env var: {}", "No Arkos-set User env vars to remove"),
        (True, "Removing arkos command...", remove_wrapper_script, "Removed {}", "No wrapper script found"),
        (windows, "Removing Windows arkos launchers...",
         remove_windows_bin_launchers, "Removed {}", "No Windows arkos launchers found"),
        (True, "Removing Arkos-managed node/npm/npx symlinks...",
         lambda: remove_node_symlinks(arkos_home), "Removed {}", "No Arkos-managed node/npm/npx symlinks found"),
    ):
        if on_this_platform:
            _remove_step(label, remove, success_fmt, none_msg)

    log_info("Removing desktop Chat GUI artifacts...")
    try:
        from arkos_cli.gui_uninstall import uninstall_gui
        if not uninstall_gui(arkos_home):
            log_info("No desktop GUI artifacts found")
    except Exception as e:
        log_warn(f"Could not remove desktop GUI artifacts: {e}")

    log_info("Removing installation directory...")
    _rmtree_step(project_root)
    if windows:
        _remove_step(
            "Removing Windows installer artifacts (PortableGit, Node, gateway-service)...",
            lambda: remove_portable_tooling_windows(arkos_home), "Removed {}",
            "No Windows installer artifacts to remove")

    if full_uninstall:
        for prof in named_profiles if remove_profiles else ():
            _uninstall_profile(prof)
        log_info("Removing configuration and data...")
        _rmtree_step(arkos_home)
    else:
        log_info(f"Keeping configuration and data in {arkos_home}")

    print()
    _print_box("│              ✓ Uninstall Complete!                      │", Colors.GREEN)
    print()

    if not full_uninstall:
        print(color("Your configuration and data have been preserved:", Colors.CYAN))
        print(f"  {arkos_home}/")
        print()
        print("To reinstall later with your existing settings:")
        print(color(_REINSTALL_HINT[windows], Colors.DIM))
        print()

    for line, col in _RELOAD_HINT[windows]:
        print(color(line, col) if col else line)
    print()
    print("Thank you for using Arkos! ⚕")
    print()


_REINSTALL_HINT = {
    True: "  iex (irm https://arkos.local/install.ps1)",
    False: "  curl -fsSL https://arkos.local/install.sh | bash"}
_RELOAD_HINT = {
    True: [("Open a new terminal (PowerShell / Windows Terminal) to pick up", Colors.YELLOW),
           ("the updated User PATH and environment variables.", Colors.YELLOW)],
    False: [("Reload your shell to complete the process:", Colors.YELLOW),
            ("  source ~/.bashrc  # or ~/.zshrc", None)]}


class _UninstallArgs:
    """Lightweight args namespace for the module entrypoint below."""

    def __init__(self, *, mode: str):
        self.gui = mode == "gui"
        self.gui_summary = False
        self.full = mode == "full"
        self.yes = True


def main(argv=None) -> int:
    """``python -m arkos_cli.uninstall --mode <gui|lite|full>``. Imports only stdlib +
    ``arkos_constants`` + ``arkos_cli.colors``, so it runs under a bare system Python (no venv)."""
    import argparse
    parser = argparse.ArgumentParser(prog="python -m arkos_cli.uninstall")
    parser.add_argument(
        "--mode", choices=["gui", "lite", "full"], required=True,
        help="gui = Chat GUI only; lite = GUI + agent, keep data; full = everything")
    args = _UninstallArgs(mode=parser.parse_args(argv).mode)
    (run_gui_uninstall if args.gui else run_uninstall)(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())



def find_shell_configs() -> list:
    """Find shell configuration files that might have PATH entries."""
    home = Path.home()
    configs = []

    candidates = [
        home / ".bashrc",
        home / ".bash_profile",
        home / ".profile",
        home / ".zshrc",
        home / ".zprofile",
    ]

    for config in candidates:
        if config.exists():
            configs.append(config)

    return configs
