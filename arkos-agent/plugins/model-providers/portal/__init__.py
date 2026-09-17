"""Arkos Portal provider profile."""

from typing import Any

from agent.portal_tags import get_affinity_scope, get_conversation_context, portal_tags
from agent.transports.codex import _cache_scope_from_session_id
from providers import register_provider
from providers.base import ProviderProfile


class PortalProfile(ProviderProfile):
    """Arkos Portal — product tags, reasoning with Portal-specific omission."""

    def resolve_aux_model(self, *, vision: bool = False) -> str:
        """Portal's tier-aware ``/api/portal/recommended-models`` pick (cached, offline-safe)."""
        try:
            from arkos_cli.models import get_portal_recommended_aux_model

            return get_portal_recommended_aux_model(vision=vision) or ""
        except Exception:
            return ""

    def build_extra_body(self, *, session_id: str | None = None, **context) -> dict[str, Any]:
        body: dict[str, Any] = {"tags": portal_tags(session_id=session_id)}
        sticky_key = _cache_scope_from_session_id(get_affinity_scope() or get_conversation_context() or session_id)
        if sticky_key:
            body["session_id"] = sticky_key
        return body

    @staticmethod
    def _cannot_disable_reasoning(model: str | None) -> bool:
        """True when ``reasoning: {enabled: false}`` would 400 on *model*. Cache-only catalog
        lookup; unknown/cold (warmer kicked) and no-reasoning routes both answer True (omit > 400)."""
        try:
            from arkos_cli.models_reasoning_caps import portal_model_reasoning_capabilities, warm_portal_reasoning_caps_async

            caps = portal_model_reasoning_capabilities(model)
            if caps is None:
                warm_portal_reasoning_caps_async()
                return True
        except Exception:
            return True
        return not caps.get("supports_reasoning") or bool(caps.get("mandatory"))

    def build_api_kwargs_extras(
        self, *, reasoning_config: dict | None = None, supports_reasoning: bool = False,
        model: str | None = None, **context,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Pass the full reasoning_config, disable included (the Portal honors it;
        omitting it means the upstream default, thinking ON for V4-class models)."""
        if not supports_reasoning:
            return {}, {}
        if reasoning_config is None:
            return {"reasoning": {"enabled": True, "effort": "medium"}}, {}
        rc = dict(reasoning_config)
        if rc.get("enabled") is False and self._cannot_disable_reasoning(model):
            return {}, {}
        return {"reasoning": rc}, {}


