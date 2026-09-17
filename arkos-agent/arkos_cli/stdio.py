"""Windows-safe stdio configuration.

Forces UTF-8 on the Python side and also flips the console's code page to UTF-8 (65001). Both
matter: Python-level only helps when Python's stdout is a real TTY; code-page flipping lets
subprocesses and child Python ``print()`` calls agree on encoding.
"""

from __future__ import annotations

import os
import sys

__all__ = ["configure_windows_stdio", "is_windows"]

_CONFIGURED = False


def is_windows() -> bool:
    """Return True iff running on native Windows (not WSL)."""
    return sys.platform == "win32"


def _flip_console_code_page_to_utf8() -> None:
    """``SetConsoleCP``/``SetConsoleOutputCP`` to CP_UTF8 (65001). Silent on failure: without an
    attached console (redirected stdout, service, PTY-less CI) the calls return 0 and we move on."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.SetConsoleCP(65001)
        kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass


def _reconfigure_stream(stream, *, encoding: str = "utf-8", errors: str = "replace") -> None:
    """Reconfigure a text stream to UTF-8 in place; skips streams without ``reconfigure`` (e.g. an
    ``io.StringIO`` substituted during tests)."""
    try:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding=encoding, errors=errors)
    except Exception:
        pass


def configure_windows_stdio() -> bool:
    """Force UTF-8 stdio on Windows. No-op elsewhere.

    Idempotent; returns ``True`` only when something actually changed. Set
    ``ARKOS_DISABLE_WINDOWS_UTF8=1`` to opt out (forces the old cp1252 path for diagnosing
    encoding bugs). Also sets a default ``EDITOR`` on Windows if none is set.
    """
    global _CONFIGURED

    if _CONFIGURED:
        return False
    if not is_windows() or os.environ.get("ARKOS_DISABLE_WINDOWS_UTF8") in {"1", "true", "True", "yes"}:
        _CONFIGURED = True
        return False

    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")

    _default_editor = _default_windows_editor()
    if _default_editor and not os.environ.get("EDITOR") and not os.environ.get("VISUAL"):
        os.environ["EDITOR"] = _default_editor

    _augment_path_with_known_tools()
    _flip_console_code_page_to_utf8()
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        _reconfigure_stream(stream)
    _CONFIGURED = True
    return True


def _default_windows_editor() -> str:
    """Windows default for ``$EDITOR``: ``notepad`` (ships with every install, blocks until the
    window closes). The bare name keeps prompt_toolkit's shlex split away from paths with spaces;
    "" when even notepad is missing (WinPE, Nano Server) so prompt_toolkit's no-op applies."""
    import shutil
    return "notepad" if shutil.which("notepad") else ""


def _augment_path_with_known_tools() -> None:
    r"""Prepend Arkos-managed tool directories to ``PATH`` (no-op on POSIX / missing dirs).

    install.ps1 adds entries like ``%LOCALAPPDATA%\arkos\git\bin`` to the User PATH via
    ``SetEnvironmentVariable``, but already-running shells never see that broadcast, so a arkos
    launched from the install session would not find rg / bash / grep. Prepending the known dirs
    at startup closes that first-launch gap.
    """
    if not is_windows():
        return
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if not local_appdata:
        return

    candidate_dirs = [
        os.path.join(local_appdata, "arkos", "bin"),
        os.path.join(local_appdata, "arkos", "git", "cmd"),
        os.path.join(local_appdata, "arkos", "git", "bin"),
        os.path.join(local_appdata, "arkos", "git", "usr", "bin"),
        os.path.join(local_appdata, "arkos", "arkos-agent", "venv", "Scripts"),
        os.path.join(local_appdata, "arkos", "bin"),
        os.path.join(local_appdata, "arkos", "git", "cmd"),
        os.path.join(local_appdata, "arkos", "git", "bin"),
        os.path.join(local_appdata, "arkos", "git", "usr", "bin"),
        os.path.join(local_appdata, "arkos", "arkos-agent", "venv", "Scripts"),
        os.path.join(local_appdata, "Microsoft", "WinGet", "Links")]
    existing = os.environ.get("PATH", "")
    existing_lower = {p.lower() for p in existing.split(os.pathsep) if p}
    prepend = [d for d in candidate_dirs if os.path.isdir(d) and d.lower() not in existing_lower]
    if prepend:
        os.environ["PATH"] = os.pathsep.join([*prepend, existing])
