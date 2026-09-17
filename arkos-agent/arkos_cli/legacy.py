"""Legacy migration CLI commands."""
from __future__ import annotations

import sys
from pathlib import Path


def legacy_command(args, config: dict | None = None) -> int:
    print("No legacy migrations to perform.")
    return 0
