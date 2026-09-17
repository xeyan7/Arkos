"""Resolve ARKOS_HOME for standalone skill scripts.

Skill scripts may run outside the Arkos process (e.g. system Python,
nix env, CI) where ``arkos_constants`` is not importable.  This module
provides the same ``get_arkos_home()`` and ``display_arkos_home()``
contracts as ``arkos_constants`` without requiring it on ``sys.path``.

When ``arkos_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``arkos_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``ARKOS_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from arkos_constants import display_arkos_home as display_arkos_home
    from arkos_constants import get_arkos_home as get_arkos_home
    get_arkos_home = get_arkos_home
    display_arkos_home = display_arkos_home
except (ModuleNotFoundError, ImportError):

    def get_arkos_home() -> Path:
        """Return the Arkos home directory (default: ~/.arkos)."""
        val = os.environ.get("ARKOS_HOME", "").strip()
        return Path(val) if val else Path.home() / ".arkos"

    def display_arkos_home() -> str:
        """Return a user-friendly ``~/``-shortened display string."""
        home = get_arkos_home()
        try:
            return "~/" + home.relative_to(Path.home()).as_posix()
        except ValueError:
            return str(home)

    get_arkos_home = get_arkos_home
    display_arkos_home = display_arkos_home
