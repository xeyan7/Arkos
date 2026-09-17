"""Child-process environment for execute_code: env scrubbing, interpreter and cwd resolution.

Both the per-call remote path and the local session kernel build their child
env through ``_build_child_env`` so the security rules (secret scrubbing,
PYTHONPATH hygiene, UTF-8 forcing, TZ) cannot drift between them.
"""

import logging
import os
import platform
import subprocess
import sys
from typing import Dict

logger = logging.getLogger("tools.code_execution_tool")

_IS_WINDOWS = platform.system() == "Windows"

_SAFE_ENV_PREFIXES = ("PATH", "HOME", "USER", "LANG", "LC_", "TERM", "TMPDIR", "TMP", "TEMP", "SHELL",
                      "LOGNAME", "XDG_", "PYTHONPATH", "VIRTUAL_ENV", "CONDA")
_SECRET_SUBSTRINGS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "PASSWD", "AUTH", "DSN",
                      "WEBHOOK", "CREDS", "BEARER", "APIKEY")

_ARKOS_CHILD_ALLOWED = frozenset({
    "ARKOS_HOME", "ARKOS_PROFILE", "ARKOS_CONFIG", "ARKOS_ENV", "ARKOS_DELEGATED_CHILD_CONTEXT",
})

_WINDOWS_ESSENTIAL_ENV_VARS = frozenset({
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "OS",
    "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS", "PUBLIC", "ALLUSERSPROFILE",
    "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432",
    "APPDATA", "LOCALAPPDATA", "USERPROFILE", "USERDOMAIN", "USERNAME",
    "HOMEDRIVE", "HOMEPATH", "COMPUTERNAME",
})


def _scrub_child_env(source_env, is_passthrough=None, is_windows=None):
    """Produce the scrubbed child-process env for execute_code.

    Rules, in order: (1) passthrough vars (skill/config-declared) resolve
    through the active profile secret scope — an absent scoped value is
    omitted; (2) secret-substring names are blocked; (3) safe prefixes pass;
    (4) operational ARKOS_* pass by exact name; (5) on Windows the
    OS-essential allowlist passes by exact name.
    """
    try:
        from tools.env_passthrough import is_env_passthrough, resolve_passthrough_value
    except Exception:
        is_env_passthrough = lambda _: False  # noqa: E731
        resolve_passthrough_value = lambda _name, _fallback: None  # noqa: E731
    if is_passthrough is None:
        is_passthrough = is_env_passthrough
    if is_windows is None:
        is_windows = _IS_WINDOWS
    scrubbed = {}
    _dropped_arkos = []
    for k, v in source_env.items():
        if is_passthrough(k):
            resolved = resolve_passthrough_value(k, v)
            if resolved is not None:
                scrubbed[k] = resolved
            continue
        if any(s in k.upper() for s in _SECRET_SUBSTRINGS):
            continue
        if (any(k.startswith(p) for p in _SAFE_ENV_PREFIXES)
                or k in _ARKOS_CHILD_ALLOWED
                or (is_windows and k.upper() in _WINDOWS_ESSENTIAL_ENV_VARS)):
            scrubbed[k] = v
        elif k.startswith("ARKOS_"):
            _dropped_arkos.append(k)
    if _dropped_arkos:
        logger.debug(
            "execute_code: dropped %d non-allowlisted ARKOS_* var(s) from the "
            "sandbox child env (%s). This is intentional hardening; if "
            "a sandbox script legitimately needs one, declare it via "
            "env_passthrough in the skill/config so it passes by explicit opt-in.",
            len(_dropped_arkos), ", ".join(sorted(_dropped_arkos)),
        )
    from agent.delegation_context import (
        DELEGATED_CHILD_ENV_MARKER, delegated_child_subprocess_env,
    )
    scoped = delegated_child_subprocess_env(source_env)
    if scoped.get(DELEGATED_CHILD_ENV_MARKER):
        for key in (DELEGATED_CHILD_ENV_MARKER, "ARKOS_KANBAN_DB", "ARKOS_KANBAN_BOARD"):
            if key in scoped:
                scrubbed[key] = scoped[key]
    return delegated_child_subprocess_env(scrubbed)


def _build_child_env(*, rpc_endpoint: str, rpc_token: str, tmpdir: str,
                     child_python: str) -> Dict[str, str]:
    """Build the scrubbed child environment both execution paths share."""
    from arkos_constants import apply_subprocess_home_env
    child_env = _scrub_child_env(os.environ)
    child_env["ARKOS_RPC_SOCKET"] = rpc_endpoint
    child_env["ARKOS_RPC_TOKEN"] = rpc_token
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"
    _tz_name = os.getenv("ARKOS_TIMEZONE", "").strip()
    if _tz_name:
        child_env["TZ"] = _tz_name
    child_env.pop("ARKOS_TIMEZONE", None)
    apply_subprocess_home_env(child_env)
    from tools.environments.local_pythonpath import _strip_arkos_owned_pythonpath
    _strip_arkos_owned_pythonpath(child_env)
    _existing_pp = child_env.get("PYTHONPATH", "")
    _pp_parts = [tmpdir]
    if _uses_arkos_python_environment(child_python):
        _pp_parts.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    elif child_python not in _external_env_logged:
        _external_env_logged.add(child_python)
        logger.info("execute_code: child interpreter %s is outside the Arkos "
                    "environment; arkos root omitted from PYTHONPATH", child_python)
    if _existing_pp:
        _pp_parts.append(_existing_pp)
    child_env["PYTHONPATH"] = os.pathsep.join(_pp_parts)
    return child_env


_PROBE_CACHE_MAX = 32
_usable_python_cache: dict = {}
_python_prefix_cache: dict = {}

_external_env_logged: set = set()


def _cache_probe_result(cache: dict, key: str, value):
    """Insert into a bounded probe cache, FIFO-evicting at the cap."""
    if len(cache) >= _PROBE_CACHE_MAX:
        cache.pop(next(iter(cache)))
    cache[key] = value


def _probe_python(python_path: str, code: str, *, text: bool = False):
    """Run ``python_path -c code``; None if missing, unspawnable, or past the 5s timeout."""
    try:
        from agent.delegation_context import delegated_child_subprocess_env
        return subprocess.run(
            [python_path, "-c", code], timeout=5, capture_output=True, text=text,
            creationflags=subprocess.CREATE_NO_WINDOW if _IS_WINDOWS else 0,
            stdin=subprocess.DEVNULL, env=delegated_child_subprocess_env(),
        )
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return None


def _is_usable_python(python_path: str) -> bool:
    """Whether the interpreter is Python 3.8+ (what the RPC stubs need); success cached, failure retried."""
    cached = _usable_python_cache.get(python_path)
    if cached is not None:
        return cached
    result = _probe_python(python_path, "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)")
    if result is None:
        return False
    usable = result.returncode == 0
    _cache_probe_result(_usable_python_cache, python_path, usable)
    return usable


def _python_environment_prefix(python_path: str) -> str:
    """Resolved ``sys.prefix`` reported by *python_path* ("" on failure; failures are not cached)."""
    cached = _python_prefix_cache.get(python_path)
    if cached is not None:
        return cached
    result = _probe_python(python_path, "import sys; print(sys.prefix)", text=True)
    if result is not None and result.returncode == 0 and result.stdout.strip():
        prefix = os.path.realpath(result.stdout.strip())
        _cache_probe_result(_python_prefix_cache, python_path, prefix)
        return prefix
    return ""


def _uses_arkos_python_environment(python_path: str) -> bool:
    """Whether *python_path* belongs to Arkos's active Python environment. Short-circuits when
    it IS the running interpreter (by path or realpath — covers ``uv run`` venvs) so no probe
    runs on the default strict path and a flaky probe can never drop the arkos root."""
    if python_path == sys.executable or os.path.realpath(python_path) == os.path.realpath(sys.executable):
        return True
    return _python_environment_prefix(python_path) == os.path.realpath(sys.prefix)


def _resolve_child_python(mode: str) -> str:
    """Child interpreter: ``sys.executable`` in strict mode; in project mode the active
    VIRTUAL_ENV/CONDA_PREFIX python if it exists and passes the 3.8+ probe, else ``sys.executable``."""
    if mode != "project":
        return sys.executable
    subdir, exe_names = ("Scripts", ("python.exe", "python3.exe")) if _IS_WINDOWS else ("bin", ("python", "python3"))
    for var in ("VIRTUAL_ENV", "CONDA_PREFIX"):
        root = os.environ.get(var, "").strip()
        for exe in exe_names if root else ():
            candidate = os.path.join(root, subdir, exe)
            if not (os.path.isfile(candidate) and os.access(candidate, os.X_OK)):
                continue
            if _is_usable_python(candidate):
                return candidate
            logger.info("execute_code: skipping %s=%s (Python version < 3.8 or broken). "
                        "Using sys.executable instead.", var, candidate)
            return sys.executable
    return sys.executable


def _resolve_child_cwd(mode: str, staging_dir: str, task_id: str = "") -> str:
    """Child cwd. Strict: the staging dir. Project mirrors the terminal/file-tool ladder so every
    file-writing path agrees: session cwd record (`cd` state) → registered ``session.cwd.set``
    override → TERMINAL_CWD → os.getcwd → staging dir (never Popen on a missing cwd).
    """
    if mode != "project":
        return staging_dir
    if task_id:
        try:
            from tools.terminal_tool import get_session_cwd
            recorded = get_session_cwd(task_id)
        except Exception:
            recorded = None
        if recorded and os.path.isdir(recorded):
            return recorded
        try:
            from tools.file_tools_paths import _registered_task_cwd_override
            session_cwd = _registered_task_cwd_override(task_id)
        except Exception:
            session_cwd = None
        if session_cwd and os.path.isdir(session_cwd):
            return session_cwd
    from agent.runtime_cwd import scope_terminal_cwd
    raw = scope_terminal_cwd().strip()
    for candidate in (os.path.expanduser(raw) if raw else "", os.getcwd()):
        if candidate and os.path.isdir(candidate):
            return candidate
    return staging_dir
