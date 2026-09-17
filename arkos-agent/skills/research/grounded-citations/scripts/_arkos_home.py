"""Resolve ARKOS_HOME for standalone skill scripts.

Skill scripts may run outside the Arkos process (system Python, nix env,
CI) where ``arkos_constants`` is not importable.  This module provides the
same ``get_arkos_home()`` contract without requiring it on ``sys.path``.

When ``arkos_constants`` IS available it is used directly so profile
resolution and any future enhancements are picked up automatically.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from arkos_constants import get_arkos_home as get_arkos_home
    get_arkos_home = get_arkos_home
except (ModuleNotFoundError, ImportError):

    def get_arkos_home() -> Path:
        """Return the Arkos home directory (default: ``~/.arkos``)."""
        val = os.environ.get("ARKOS_HOME", "").strip()
        return Path(val) if val else Path.home() / ".arkos"

    get_arkos_home = get_arkos_home
