"""Legacy migration subcommand parser."""
from __future__ import annotations

from typing import Callable


def build_legacy_parser(subparsers, *, cmd_legacy: Callable) -> None:
    """Attach the legacy migration subcommand to subparsers."""
    legacy_parser = subparsers.add_parser(
        "legacy", help="Legacy migration tools",
        description="Migrate settings, memories, skills, and API keys")
    legacy_parser.set_defaults(func=cmd_legacy)
