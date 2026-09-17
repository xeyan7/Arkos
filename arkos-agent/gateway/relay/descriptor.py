"""CapabilityDescriptor — the relay handshake payload. EXPERIMENTAL.

The connector hands one to the gateway's ``RelayAdapter`` at handshake: which
platform it fronts and which capabilities to advertise to the stream consumer
(char limit, draft streaming, edit/threading, markdown dialect, length unit), so
one adapter serves every platform without per-platform branching. Schema evolution
is additive-only, gated by ``contract_version`` (docs/relay-connector-contract.md).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

CONTRACT_VERSION = 1


@dataclass(frozen=True)
class CapabilityDescriptor:
    """Immutable capability profile negotiated at relay handshake (frozen: fixed for the connection)."""

    contract_version: int
    platform: str
    label: str
    max_message_length: int
    supports_draft_streaming: bool
    supports_edit: bool
    supports_threads: bool
    markdown_dialect: str
    len_unit: str
    emoji: str = "\U0001f50c"
    platform_hint: str = ""
    pii_safe: bool = False
    supports_context: bool = False
    supports_inchannel_continuable: bool = False
    supports_block_formatting: bool = False
    supported_ops: tuple = ()

    LEGACY_OPS = ("send", "edit", "typing", "follow_up")

    def supports_op(self, op: str) -> bool:
        """Whether the connector advertises ``op`` (legacy set when none advertised).

        A NEW op is therefore only True when explicitly advertised — capability
        can be probed without trying the op and parsing an error.
        """
        return op in (self.supported_ops or self.LEGACY_OPS)

    def to_json(self) -> str:
        """Compact, stable JSON for the handshake frame."""
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str) -> "CapabilityDescriptor":
        """Deserialize a handshake JSON string; unknown keys ignored, missing keys default.

        Trust-boundary normalization (malformed input never breaks the handshake):
        a non-positive/garbage ``max_message_length`` ("no limit", or hostile)
        maps to the documented 4096 default so the adapter can always chunk;
        ``supported_ops`` becomes a tuple of non-empty strings, or () (legacy
        fallback) when malformed.
        """
        raw = json.loads(data)
        known = cls.__dataclass_fields__  # type: ignore[attr-defined]
        filtered = {k: v for k, v in raw.items() if k in known}
        if "max_message_length" in filtered:
            try:
                if int(filtered["max_message_length"]) <= 0:
                    filtered["max_message_length"] = 4096
            except (TypeError, ValueError):
                filtered["max_message_length"] = 4096
        if "supported_ops" in filtered:
            raw_ops = filtered["supported_ops"]
            filtered["supported_ops"] = (
                tuple(str(op) for op in raw_ops if isinstance(op, str) and op)
                if isinstance(raw_ops, (list, tuple))
                else ()
            )
        return cls(**filtered)
