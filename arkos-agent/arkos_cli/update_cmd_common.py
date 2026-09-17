"""Shared leaf helpers for the ``arkos update`` modules (no Arkos imports; no cycle)."""

import logging
from contextlib import contextmanager

logger = logging.getLogger("arkos_cli.update_cmd")


@contextmanager
def _best_effort(message: str):
    """Run a non-critical update step; swallow ``Exception`` and log it at debug.

    The updater must never die on bookkeeping (receipt, notices, cache seeds):
    ``message`` is the ``%s``-style debug line the inline ``try/except`` used.
    """
    try:
        yield
    except Exception as exc:
        logger.debug(message, exc)
