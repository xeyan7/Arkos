"""Install and remove the Linux desktop entry (``arkos.desktop``).

The entry must be launch-context independent: ``Exec=`` is an absolute launcher that survives the
venv (no ``#!/usr/bin/env python3`` escapes, no checkout-internal argv[0]), and ``Icon=`` is the
themed name backed by a copy in the user's hicolor tree. Cache refresh is best-effort and
tool-gated (``update-desktop-database``, ``gtk-update-icon-cache``, ``kbuildsycoca6``/``5``); a
missing tool is not an error.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Optional

DESKTOP_ENTRY_NAME = "arkos.desktop"

_SHELL_NAMES = ("bash", "sh", "dash", "zsh", "ksh")


def is_supported() -> bool:
    """XDG desktop entries exist only on Linux and BSD."""
    return sys.platform.startswith(("linux", "freebsd", "openbsd", "netbsd"))


def _xdg_data_home() -> Path:
    raw = os.environ.get("XDG_DATA_HOME")
    return Path(raw).expanduser() if raw and raw.strip() else Path.home() / ".local" / "share"


def desktop_entry_path() -> Path:
    return _xdg_data_home() / "applications" / DESKTOP_ENTRY_NAME


def icon_path(project_root: Path) -> Path:
    return project_root / "apps" / "desktop" / "assets" / "icon.png"


def _running_interpreter() -> str:
    """Venv-semantic interpreter path for the persisted ``Exec=`` line.

    ``sys.executable`` inside a venv is commonly a SYMLINK into a shared base-interpreter tree
    (uv, pyenv, conda). ``resolve`` follows it out of the venv, and CPython discovers
    ``pyvenv.cfg`` from the *lexical* argv[0] — so a dereferenced path boots without the venv's
    site-packages. Keep the lexical form when any ancestor holds a ``pyvenv.cfg``.
    """
    lexical = os.path.abspath(sys.executable)
    path = Path(lexical)
    if any((base / "pyvenv.cfg").is_file() for base in (path.parent, *path.parent.parents)):
        return lexical
    return str(path.resolve())


_probe_cache: "dict[str, bool]" = {}


def _can_import_arkos_cli(interpreter: Path) -> bool:
    """Whether *interpreter* can import ``arkos_cli.main`` unaided.

    Runs under ``-I`` (no user site, no PYTHONPATH, no cwd on ``sys.path``) from a neutral cwd, so
    the answer matches a cold desktop environment. Cached per process; an unprobeable interpreter
    (missing binary, spawn failure, timeout) is assumed capable and deliberately NOT cached, so one
    transient hiccup doesn't freeze the assumption for the session.
    """
    key = str(interpreter)
    if key in _probe_cache:
        return _probe_cache[key]
    ok = _run_quiet(
        [key, "-I", "-c", "import arkos_cli.main"],
        cwd=os.path.abspath(os.sep), timeout=15, on_error=None,
    )
    if ok is None:
        return True
    _probe_cache[key] = ok
    return ok


def _running_interpreter_fallback() -> str:
    """The RUNNING interpreter — it has ``arkos_cli`` importable by definition."""
    return os.path.abspath(sys.executable)


def resolve_exec_command(project_root: Optional[Path] = None) -> str:
    """Build the absolute ``Exec=`` command line for ``arkos desktop``.

    Prefer the real ``arkos`` launcher; fall back to ``<python> -m arkos_cli.main desktop``.
    """
    from arkos_cli.relaunch import resolve_arkos_bin

    bin_path = _resolve_arkos_bin_for_desktop_entry(resolve_arkos_bin, checkout_root=project_root)
    interpreter = _running_interpreter()
    if not _can_import_arkos_cli(Path(interpreter)):
        interpreter = _running_interpreter_fallback()
    argv = [interpreter, "-m", "arkos_cli.main", "desktop"]
    if bin_path:
        resolved = Path(bin_path).resolve()
        prefix = [interpreter] if _needs_interpreter(resolved) else []
        argv = [*prefix, str(resolved), "desktop"]
    return " ".join(_quote_exec_arg(a) for a in argv)


def _is_interpreter(candidate: Path) -> bool:
    """A python interpreter binary (``bin/python*``), not a launcher: strict basename match
    (rejects ``python3-config``, ``pythonw``) inside a bin/Scripts dir (rejects a stray script
    named ``python`` elsewhere).

    Regex approach proposed independently in 94051; kept here with the parent-dir guard so a script named
    ``python`` outside a bin/Scripts tree is not misclassified..
    """
    return bool(re.fullmatch(r"python[23]?(\d+)?(\.\d+)?", candidate.name.lower())) and (
        candidate.parent.name in {"bin", "scripts"}
    )


def _inside_checkout(candidate: str, checkout_root: Path, original_argv0: str) -> bool:
    """Whether a launcher candidate is a launch-context artifact rather than a durable launcher."""
    try:
        path = Path(candidate).resolve()
    except OSError:
        return False
    try:
        resolved_root = checkout_root.resolve()
    except OSError:
        resolved_root = None
    for root in {checkout_root, resolved_root}:
        if root is not None and (path == root or root in path.parents):
            return True
    try:
        return path.samefile(original_argv0) and _is_interpreter(path)
    except OSError:
        return False


def _resolve_arkos_bin_for_desktop_entry(
    resolve_fn=None,
    checkout_root: Optional[Path] = None,
) -> Optional[str]:
    """Resolve the launcher binary for the persisted ``.desktop`` entry.

    Wraps :func:`arkos_cli.relaunch.resolve_arkos_bin` with one rule: an ``argv[0]`` inside this
    checkout is a launch-context artifact, not a durable installed launcher — persisting it makes
    the entry depend on how the previous launch happened (a bootstrap loop). Skip such candidates
    and fall through to PATH, then to the installer's known wrapper locations. ``resolve_fn`` is
    injectable for tests..
    """
    if resolve_fn is None:
        from arkos_cli.relaunch import resolve_arkos_bin as resolve_fn

    if checkout_root is None:
        checkout_root = _project_root()
    checkout_root = Path(os.path.abspath(checkout_root))
    module_lexical_root = _project_root()
    original_argv0 = sys.argv[0]

    primary = resolve_fn()
    if primary and not _inside_checkout(primary, checkout_root, original_argv0):
        return primary

    sys.argv[0] = ""
    try:
        rerouted = resolve_fn()
    finally:
        sys.argv[0] = original_argv0

    if not primary:
        return primary
    if rerouted is not None:
        return rerouted or primary

    for candidate in _known_wrapper_candidates():
        if (
            candidate.is_file()
            and os.access(candidate, os.X_OK)
            and _wrapper_shebang_safe(candidate)
            and (
                _wrapper_targets_checkout(candidate, checkout_root)
                or _wrapper_targets_checkout(candidate, module_lexical_root)
            )
        ):
            return str(candidate)
    return None


def _shebang_tokens(shebang: str) -> "list[str]":
    return shebang[2:].strip().split()


def _is_native_binary(head: bytes) -> bool:
    return head[:4] == b"\x7fELF" or head.startswith(b"MZ")


def _read_head(path: Path, size: int = 4096) -> Optional[bytes]:
    try:
        with open(path, "rb") as fh:
            return fh.read(size)
    except OSError:
        return None


def _wrapper_shebang_safe(wrapper: Path) -> bool:
    """Whether an executable wrapper can actually run in the DE context.

    Native binaries and shell launchers are safe by construction (the shell script execs the right
    interpreter itself). A python-shebang wrapper is safe only when its interpreter stays inside
    the RUNNING venv; anything unknown fails safe toward the module fallback.
    """
    head = _read_head(wrapper)
    if head is None:
        return False
    if _is_native_binary(head):
        return True
    if not head.startswith(b"#!"):
        return False
    shebang = head.decode("utf-8", errors="replace").splitlines()[0]
    tokens = _shebang_tokens(shebang)
    if not tokens:
        return False
    interp = Path(tokens[0])
    if interp.name == "env":
        target = next((Path(t) for t in tokens[1:] if not t.startswith("-")), Path(""))
        return target.name in _SHELL_NAMES or not _shebang_escapes_running_env(shebang)
    if interp.name in _SHELL_NAMES:
        return True
    if "python" not in interp.name.lower():
        return False
    return not _shebang_escapes_running_env(shebang)


_ROOT_TERMINATORS = ('"', "'", " ", "\n", "\t", "\r", "$", "\x00", "/")


def _wrapper_targets_checkout(wrapper: Path, checkout_root: Path) -> bool:
    """Whether a candidate launcher script actually launches THIS checkout.

    Boundary-aware: a bare substring test would also accept sibling paths that EXTEND this
    checkout's path (``<checkout>-old``, ``<checkout>.bak``), so the root must end at a quote /
    whitespace / EOL or continue INTO the tree (``<root>/``). Both lexical and resolved roots are
    tried: the installer writes $INSTALL_DIR lexically, so with a symlinked home the shim text
    carries the lexical path while the caller may pass a resolved one.
    """
    head = _read_head(wrapper)
    if head is None:
        return False
    if _is_native_binary(head):
        return True
    text = head.decode("utf-8", errors="replace")
    lexical_root = os.path.abspath(str(checkout_root))
    roots = {str(checkout_root), lexical_root}
    try:
        roots.add(str(Path(lexical_root).resolve()))
    except OSError:
        pass
    stripped = text.rstrip("\r\n")
    return any(
        stripped.endswith(root) or any(root + t in text for t in _ROOT_TERMINATORS)
        for root in roots
    )


def _known_wrapper_candidates():
    """Durable installed-launcher locations, most likely first.

    Mirrors the installer's ``get_command_link_dir()`` layouts: Termux (``$PREFIX/bin``), root FHS
    (``/usr/local/bin``), and user (``~/.local/bin``). The wrapper is always named ``arkos``.
    """
    candidates = []
    prefix = os.environ.get("PREFIX")
    if prefix:
        candidates.append(Path(prefix) / "bin" / "arkos")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        candidates.append(Path("/usr/local/bin/arkos"))
    candidates.append(Path.home() / ".local" / "bin" / "arkos")
    return candidates


def _project_root() -> Path:
    """``<checkout>`` from this file's location — lexical (no ``.resolve()``) so shim-text matching
    against the installer's lexically-written $INSTALL_DIR works on symlinked homes."""
    return Path(os.path.abspath(__file__)).parent.parent


def _needs_interpreter(bin_path: Path) -> bool:
    """Whether ``bin_path`` is a Python script whose shebang escapes the running venv.

    Native binaries (uv shim, PyInstaller, distro package) and shell wrappers (the installer's
    bash launcher execs the venv python itself) never need one.
    """
    head = _read_head(bin_path, 256)
    if head is None or not head.startswith(b"#!"):
        return False
    shebang = head.decode("utf-8", errors="replace").splitlines()[0].strip()
    if "python" not in shebang.lower():
        return False
    return _shebang_escapes_running_env(shebang)


def _shebang_escapes_running_env(shebang: str) -> bool:
    """Whether a python shebang resolves OUTSIDE the running interpreter's directory.

    Compares PATH COMPONENTS, never substrings: ``<venv>/bin-extra/python`` is not inside
    ``<venv>/bin``. ``env`` shebangs ALWAYS escape — ``env`` resolves through the DE's cold PATH,
    not the shell that installed the venv — except the rare ``env -S <abs-interpreter>`` form,
    which is judged by its absolute target.

    Tokenizes the shebang (interpreter path plus any flags) and compares PATH COMPONENTS, never substrings:
    ``<venv>/bin-extra/python`` is not inside ``<venv>/bin`` even though it starts with it
    (sibling-directory confusion guard).
    The comparison uses the LEXICAL interpreter directory (abspath, not resolve): on uv venvs the resolved
    parent is the base interpreter's dir, which makes a valid ``.venv/bin/python`` shebang look foreign
    (review case 1). Both sides use the SAME case operation (``.lower``): interpreter paths
    legitimately carry uppercase (conda env names, usernames, uv's ephemeral build dirs) and an asymmetric
    compare would flag the venv's own console script as foreign.
    """
    tokens = _shebang_tokens(shebang)
    if not tokens:
        return True
    interp = Path(tokens[0])
    if interp.name in ("env", "env.exe"):
        rest = [t for t in tokens[1:] if not t.startswith("-")]
        if not (rest and Path(rest[0]).is_absolute()):
            return True
        interp = Path(rest[0])
    running_dir = os.path.dirname(os.path.abspath(sys.executable)).lower()
    return str(interp.parent).lower() != running_dir


def _quote_exec_arg(arg: str) -> str:
    """Quote one ``Exec`` argument per the desktop entry spec."""
    if not any(c in arg for c in " \t\n\"'\\><~|&;$*?#()`"):
        return arg
    escaped = arg.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_desktop_entry(exec_command: str, icon: str) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Arkos\n"
        "GenericName=Arkos Desktop\n"
        "Comment=Launch Arkos Desktop\n"
        f"Exec={exec_command}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
        "StartupNotify=true\n"
        "StartupWMClass=Arkos\n"
    )


def refresh_desktop_databases(applications_dir: Path) -> "list[str]":
    """Reindex the menu caches. Run each tool only when it exists."""
    ran: list[str] = []

    update_db = shutil.which("update-desktop-database")
    if update_db and _run_quiet([update_db, str(applications_dir)]):
        ran.append("update-desktop-database")

    for tool in ("kbuildsycoca6", "kbuildsycoca5"):
        resolved = shutil.which(tool)
        if resolved:
            if _run_quiet([resolved, "--noincremental"]):
                ran.append(tool)
            break

    return ran


def _run_quiet(cmd: "list[str]", *, timeout: int = 60, on_error: Optional[bool] = False, **kwargs) -> Optional[bool]:
    """Exit-status success of a silenced subprocess; ``on_error`` when it could not be run at all."""
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout,
            **kwargs,
        )
    except (OSError, subprocess.SubprocessError):
        return on_error
    return result.returncode == 0


_HICOLOR_INDEXED_SIZES = (16, 22, 24, 32, 36, 48, 64, 72, 96, 128, 192, 256, 512)
_HICOLOR_INSTALL_SIZES = (24, 32, 48, 256)


def _png_dimensions(raw: bytes) -> Optional[tuple[int, int]]:
    """``(width, height)`` from a PNG IHDR, or ``None`` if unreadable."""
    if len(raw) >= 24 and raw[:8] == b"\x89PNG\r\n\x1a\n" and raw[12:16] == b"IHDR":
        return struct.unpack(">II", raw[16:24])
    return None


def _hicolor_subdir(dimensions: Optional[tuple[int, int]]) -> str:
    """Pick a fixed-size hicolor dir the theme indexes. Never ``scalable``."""
    if dimensions is None:
        return "256x256"
    width, height = dimensions
    if width in _HICOLOR_INDEXED_SIZES and width == height:
        return f"{width}x{width}"
    if width != height or width <= 0 or width > 256:
        return "256x256"
    nearest = min(_HICOLOR_INDEXED_SIZES, key=lambda size: abs(size - width))
    return f"{nearest}x{nearest}"


def _hicolor_icon_dest(subdir: str) -> Path:
    return _xdg_data_home() / "icons" / "hicolor" / subdir / "apps" / "arkos.png"


def _remove_stale_scalable_icon() -> bool:
    """Drop a leftover PNG from ``scalable/`` (the pre-fix install path); True if removed."""
    stale = _hicolor_icon_dest("scalable")
    try:
        removed = stale.is_file()
        if removed:
            stale.unlink()
        return removed
    except OSError:
        return False


def _refresh_hicolor_cache() -> None:
    """Best-effort reindex of the user hicolor tree. Missing tool is fine."""
    hicolor = _xdg_data_home() / "icons" / "hicolor"
    for tool in ("gtk-update-icon-cache", "gtk4-update-icon-cache"):
        resolved = shutil.which(tool)
        if resolved:
            _run_quiet([resolved, "-f", "-t", str(hicolor)])
            return


def _resized_hicolor_pngs(raw: bytes) -> Optional[dict[str, bytes]]:
    """Lanczos-resize *raw* to each panel size; ``None`` when it will not decode (truncated/fake
    PNG) so the caller falls back to a copy. Pillow is imported lazily to keep the uninstaller
    import-light."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(raw)) as im:
            rgba = im.convert("RGBA")
            out: dict[str, bytes] = {}
            for size in _HICOLOR_INSTALL_SIZES:
                buf = io.BytesIO()
                rgba.resize((size, size), Image.Resampling.LANCZOS).save(buf, format="PNG")
                out[f"{size}x{size}"] = buf.getvalue()
            return out
    except (OSError, ValueError):
        return None


def _write_hicolor_pngs(files: dict[str, bytes]) -> bool:
    """Write *files* keyed by hicolor size dir. Return True if any file changed."""
    wrote = False
    for subdir, data in files.items():
        dest = _hicolor_icon_dest(subdir)
        if dest.is_file() and dest.read_bytes() == data:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        wrote = True
    return wrote


def _install_icon_to_hicolor(icon: Path) -> bool:
    """Install the app icon into the user's hicolor tree so ``Icon=arkos`` resolves without an
    absolute checkout path. Raster PNGs go to indexed fixed-size dirs, never ``scalable``."""
    try:
        raw = icon.read_bytes()
        resized = _resized_hicolor_pngs(raw)
        if resized is not None:
            wrote = _write_hicolor_pngs(resized)
        else:
            dest = _hicolor_icon_dest(_hicolor_subdir(_png_dimensions(raw)))
            wrote = not (dest.is_file() and dest.read_bytes() == raw)
            if wrote:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(icon, dest)
        if _remove_stale_scalable_icon() or wrote:
            _refresh_hicolor_cache()
        return True
    except OSError:
        return False


def _launcher_entry_management_enabled() -> bool:
    """Whether config.yaml allows rewriting an EXISTING launcher entry.

    ``desktop.manage_launcher_entry: false`` opts out of the every-launch
    rewrite: a hand-edited ``arkos.desktop`` is then left alone instead
    of silently reverting ('s clobber complaint). A MISSING entry
    is still created regardless — the opt-out protects user edits, not
    first-run presence. Any config error reads as enabled (default).
    """
    try:
        from arkos_cli.config import load_config_readonly

        desktop_cfg = (load_config_readonly() or {}).get("desktop") or {}
        raw = desktop_cfg.get("manage_launcher_entry", True)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() not in ("false", "0", "no", "off")
        return True
    except Exception:
        return True


def install_desktop_entry(project_root: Path) -> Optional[Path]:
    """Create or refresh the entry, respecting the opt-out for existing entries.

    ``None`` on non-Linux platforms or when the write fails — a convenience, never a reason to
    fail a launch.
    """
    if not is_supported():
        return None

    entry_path = desktop_entry_path()

    if entry_path.is_file() and not _launcher_entry_management_enabled():
        return entry_path

    icon = icon_path(project_root)
    icon_value = str(icon) if icon.is_file() else "arkos"
    if icon.is_file() and _install_icon_to_hicolor(icon):
        icon_value = "arkos"
    contents = render_desktop_entry(resolve_exec_command(project_root), icon_value)

    try:
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        if entry_path.is_file() and entry_path.read_text(encoding="utf-8") == contents:
            return entry_path
        from utils import atomic_write_text

        atomic_write_text(entry_path, contents, create_mode=0o755)
        entry_path.chmod(0o755)
    except OSError:
        return None

    refresh_desktop_databases(entry_path.parent)
    return entry_path
