"""Centralized Arkos Portal request tags.

Every Arkos request to the Arkos Portal (main loop, auxiliary client, fallback
paths) must carry the same product-attribution tags, sent in OpenAI-compatible
``extra_body['tags']``: ``["product=arkos-agent", "client=arkos-client-v<__version__>"]``.
The version is read live from ``arkos_cli.__version__`` — do NOT pre-compute it
as a module constant in consumers; it can change at runtime (editable installs,
hot reload).
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import List, Optional

_conversation_id: ContextVar[Optional[str]] = ContextVar("portal_conversation_id", default=None)

_affinity_scope: ContextVar[Optional[str]] = ContextVar("arkos_affinity_scope", default=None)


def _reset_var(var: ContextVar, token) -> None:
    """Reset ``var``; a token from another Context (reset on a different thread)
    falls back to clearing rather than raising in cleanup paths."""
    try:
        var.reset(token)
    except Exception:
        var.set(None)


def set_affinity_scope(scope: Optional[str]):
    """Publish the declared routing/affinity scope; returns the ContextVar token."""
    return _affinity_scope.set(scope or None)


def reset_affinity_scope(token) -> None:
    """Restore the previous affinity scope (pair with ``set_affinity_scope``)."""
    _reset_var(_affinity_scope, token)


def get_affinity_scope() -> Optional[str]:
    return _affinity_scope.get()


def set_conversation_context(conversation_id: Optional[str]):
    """Publish the active conversation id for ambient Portal tagging; returns the token.

    Called by the agent loop at turn entry with the session-lineage ROOT id (so
    the tag survives context-compression rotation). ``None`` clears.
    """
    return _conversation_id.set(conversation_id or None)


def reset_conversation_context(token) -> None:
    """Restore the previous conversation context (pair with ``set_...``)."""
    _reset_var(_conversation_id, token)


def get_conversation_context() -> Optional[str]:
    return _conversation_id.get()


def arkos_client_tag() -> str:
    """``client=arkos-client-v<MAJOR>.<MINOR>.<PATCH>`` ("unknown" if arkos_cli is unimportable)."""
    try:
        from arkos_cli import __version__
    except Exception:
        __version__ = "unknown"
    return f"client=arkos-client-v{__version__}"


def conversation_tag(session_id: str) -> str:
    """``conversation=<session_id>`` — high-cardinality, so only appended when a
    session id is actually available, never in the always-on base set."""
    return f"conversation={session_id}"


def portal_tags(session_id: str | None = None) -> List[str]:
    """Fresh list of the canonical Arkos Portal tags.

    The ambient conversation context (lineage ROOT id) wins over the explicit
    ``session_id``, a fallback for callers outside any agent turn.
    """
    tags = ["product=arkos-agent", arkos_client_tag()]
    effective = get_conversation_context() or session_id
    if effective:
        tags.append(conversation_tag(effective))
    return tags
