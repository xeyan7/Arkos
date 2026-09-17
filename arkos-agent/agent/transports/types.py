"""Shared types for normalized provider responses.

Only fields every downstream consumer reads are top-level; protocol-specific
state lives in ``provider_data`` (response-level and per-tool-call) so
protocol-aware code can reach it without widening the shared type.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """A normalized tool call from any provider.

    ``id`` is the protocol's canonical identifier (``tool_call_id`` / ``tool_use_id``);
    may be ``None`` when the provider omits it — the agent fills it via
    ``_deterministic_call_id()`` before storing history.
    ``provider_data``: Codex ``{"call_id", "response_item_id"}``, Gemini
    ``{"extra_content": {"google": {"thought_signature": ...}}}``, else ``None``.
    """

    id: str | None
    name: str
    arguments: str
    provider_data: dict[str, Any] | None = field(default=None, repr=False)

    type = property(lambda self: "function")
    function = property(lambda self: self)

    def _pd(self, key: str) -> Any:
        return (self.provider_data or {}).get(key)

    call_id = property(lambda self: self._pd("call_id"))
    response_item_id = property(lambda self: self._pd("response_item_id"))
    extra_content = property(lambda self: self._pd("extra_content"))


@dataclass
class Usage:
    """Token usage from an API response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0

    @classmethod
    def from_openai(cls, u: Any) -> Usage:
        """Build from an OpenAI-shaped usage object, treating missing/None counts as 0."""
        return cls(**{k: getattr(u, k, 0) or 0 for k in ("prompt_tokens", "completion_tokens", "total_tokens")})


@dataclass
class NormalizedResponse:
    """Normalized API response from any provider.

    Response-level ``provider_data``: Anthropic ``{"reasoning_details": [...]}``,
    Codex ``{"codex_reasoning_items": [...], "codex_message_items": [...]}``, else ``None``.
    """

    content: str | None
    tool_calls: list[ToolCall] | None
    finish_reason: str
    reasoning: str | None = None
    usage: Usage | None = None
    provider_data: dict[str, Any] | None = field(default=None, repr=False)

    def _pd(self, key: str) -> Any:
        return (self.provider_data or {}).get(key)

    reasoning_content = property(lambda self: self._pd("reasoning_content"))
    reasoning_details = property(lambda self: self._pd("reasoning_details"))
    anthropic_content_blocks = property(lambda self: self._pd("anthropic_content_blocks"))
    bedrock_content_blocks = property(lambda self: self._pd("bedrock_content_blocks"))
    codex_reasoning_items = property(lambda self: self._pd("codex_reasoning_items"))
    codex_message_items = property(lambda self: self._pd("codex_message_items"))


def build_tool_call(id: str | None, name: str, arguments: Any, **provider_fields: Any) -> ToolCall:
    """Build a ``ToolCall``; dict *arguments* are JSON-serialised, extra kwargs become ``provider_data``."""
    args_str = json.dumps(arguments) if isinstance(arguments, dict) else str(arguments)
    return ToolCall(id=id, name=name, arguments=args_str, provider_data=dict(provider_fields) if provider_fields else None)


def map_finish_reason(reason: str | None, mapping: dict[str, str]) -> str:
    """Translate a provider stop reason via *mapping*; unknown or ``None`` -> ``"stop"``."""
    return "stop" if reason is None else mapping.get(reason, "stop")
