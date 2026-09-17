"""Shared directory pruning policy for broad recursive scans.

These names identify version-control internals, dependency trees, generated
artifacts, caches, and backup copies that are not useful results for broad
agent-facing discovery. Ordinary search callers may still target an explicit
path; broad diagnostic probes should apply this policy to recursive walks.
"""

from __future__ import annotations


SEARCH_PRUNE_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "venv", ".venv", "site-packages", "dist-packages",
    "vendor", "third_party",
    "build", "dist", "target", "out", "coverage",
    ".next", ".turbo", ".parcel-cache", ".nuxt", ".svelte-kit",
    "__pycache__", ".cache", ".Trash", ".tox", ".nox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".npm", ".yarn", ".pnpm-store",
    ".gradle", ".m2", ".nuget",
    "backups", "backup", ".backups",
})
