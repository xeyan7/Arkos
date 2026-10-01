#!/usr/bin/env python3
"""Install psutil on Termux/Android by patching upstream platform detection.

psutil's setup currently gates Linux sources behind
``sys.platform.startswith('linux')``. On Termux, Python reports
``sys.platform == 'android'``, so ``pip install psutil`` aborts with
"platform android is not supported" — even though psutil compiles fine
when the Linux source path is reused.

This script downloads the official psutil sdist, applies a one-line
patch (``LINUX = sys.platform.startswith(("linux", "android"))``), and
installs the patched tree with ``pip install --no-build-isolation``.

Usage:
    python scripts/install_psutil_android.py [--pip "/path/to/pip"] [--uv]

When neither flag is given, the script auto-detects ``uv`` on PATH and
falls back to ``<sys.executable> -m pip``.

This is a stopgap. Remove once psutil upstream merges
https://github.com/giampaolo/psutil/pull/2762 and ships a release.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import tarfile
from pathlib import PurePosixPath

PSUTIL_URL = (
    "https://files.pythonhosted.org/packages/aa/c6/"
    "d1ddf4abb55e93cebc4f2ed8b5d6dbad109ecb8d63748dd2b20ab5e57ebe/psutil-7.2.2.tar.gz"
)

MARKER = 'LINUX = sys.platform.startswith("linux")'
REPLACEMENT = 'LINUX = sys.platform.startswith(("linux", "android"))'


class PsutilAndroidInstallError(RuntimeError):
    """Raised when the pinned psutil sdist is missing or unsafe."""


def _normalize_member_parts(member_name: str) -> tuple[str, ...]:
    path = PurePosixPath(member_name)
    parts = tuple(part for part in path.parts if part not in ("", "."))
    if path.is_absolute() or ".." in parts or not parts:
        raise PsutilAndroidInstallError(f"Unsafe archive member path: {member_name!r}")
    return parts


def _safe_extract_tar_gz(archive: Path, destination: Path) -> None:
    """Extract a tar.gz without allowing traversal or link members."""
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            parts = _normalize_member_parts(member.name)
            target = destination.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise PsutilAndroidInstallError(f"Unsupported archive member type: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = tf.extractfile(member)
            if extracted is None:
                raise PsutilAndroidInstallError(f"Cannot read archive member: {member.name}")
            with extracted, open(target, "wb") as dst:
                shutil.copyfileobj(extracted, dst)
            try:
                target.chmod(member.mode & 0o777)
            except OSError:
                pass


def prepare_patched_psutil_sdist(archive: Path, destination: Path) -> Path:
    """Safely extract the pinned psutil sdist and patch it for Android."""
    _safe_extract_tar_gz(archive, destination)
    src_roots = [path for path in destination.iterdir() if path.is_dir() and path.name.startswith("psutil-")]
    if not src_roots:
        raise PsutilAndroidInstallError("psutil sdist did not contain a psutil-* directory")
    src_root = min(src_roots, key=lambda path: path.name)
    common_py = src_root / "psutil" / "_common.py"
    rel = common_py.relative_to(src_root)
    if not common_py.is_file():
        raise PsutilAndroidInstallError(f"psutil sdist did not contain {rel!s}")
    try:
        content = common_py.read_text(encoding="utf-8")
    except OSError as exc:
        raise PsutilAndroidInstallError(f"Failed to read {rel!s}") from exc
    if MARKER not in content:
        raise PsutilAndroidInstallError("psutil Android compatibility patch marker not found")
    try:
        common_py.write_text(content.replace(MARKER, REPLACEMENT), encoding="utf-8")
    except OSError as exc:
        raise PsutilAndroidInstallError(f"Failed to write {rel!s}") from exc
    return src_root



def _resolve_install_cmd(pip_arg: str | None, prefer_uv: bool) -> list[str]:
    if pip_arg:
        return pip_arg.split()
    if prefer_uv:
        uv = shutil.which("uv")
        if not uv:
            sys.exit("--uv requested but no uv on PATH")
        return [uv, "pip"]
    auto_uv = shutil.which("uv")
    if auto_uv:
        return [auto_uv, "pip"]
    return [sys.executable, "-m", "pip"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pip",
        help="Explicit installer command (e.g. '/usr/bin/uv pip' or 'python -m pip')",
    )
    parser.add_argument(
        "--uv",
        action="store_true",
        help="Force using uv (errors out if uv is not on PATH)",
    )
    args = parser.parse_args()

    install_cmd_prefix = _resolve_install_cmd(args.pip, args.uv)

    print(
        "→ Termux/Android: prebuilding psutil with Linux source path "
        "compatibility shim (see )..."
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / "psutil.tar.gz"
        urllib.request.urlretrieve(PSUTIL_URL, archive)
        try:
            src_root = prepare_patched_psutil_sdist(archive, tmp_path)
        except PsutilAndroidInstallError as exc:
            sys.exit(str(exc))

        cmd = install_cmd_prefix + ["install", "--no-build-isolation", str(src_root)]
        print(f"  $ {' '.join(cmd)}")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            return result.returncode

    print("✓ psutil installed via Android compatibility shim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
