"""Arkos Gateway support library (session context, config, delivery routing).

Engine-only build: the multi-platform messaging loop, session store, and
platform adapters were removed. What remains is the plumbing the engine
imports (``session_context``, ``config``, ``status``, ...).
"""

from .config import GatewayConfig, PlatformConfig, HomeChannel, load_gateway_config
from .delivery import DeliveryRouter, DeliveryTarget

__all__ = [
    "GatewayConfig", "PlatformConfig", "HomeChannel", "load_gateway_config",
    "DeliveryRouter", "DeliveryTarget",
]
