"""Arkos Portal upstream adapter."""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, FrozenSet, Optional

from arkos_cli.auth import (
    AuthError,
    DEFAULT_PORTAL_INFERENCE_URL,
    _load_auth_store,
    _auth_store_lock,
    _is_terminal_portal_refresh_error,
    _portal_inference_env_override,
    _quarantine_portal_oauth_state,
    _quarantine_portal_pool_entries,
    _save_auth_store,
    _validate_portal_inference_url_from_network,
    _write_shared_portal_state,
    resolve_portal_runtime_credentials,
)
from arkos_cli.proxy.adapters.base import UpstreamAdapter, UpstreamCredential

logger = logging.getLogger(__name__)

_ALLOWED_PATHS: FrozenSet[str] = frozenset({"/chat/completions", "/completions", "/embeddings", "/models"})


class PortalAdapter(UpstreamAdapter):
    """Proxy upstream for the Arkos Portal inference API."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "portal"

    @property
    def display_name(self) -> str:
        return "Arkos Portal"

    @property
    def allowed_paths(self) -> FrozenSet[str]:
        return _ALLOWED_PATHS

    def is_authenticated(self) -> bool:
        state = self._read_state() or {}
        return bool(state.get("agent_key") or (state.get("refresh_token") and state.get("access_token")))

    def get_credential(self) -> UpstreamCredential:
        return self._get_credential()

    def get_retry_credential(
        self, *, failed_credential: UpstreamCredential, status_code: int
    ) -> Optional[UpstreamCredential]:
        if status_code != 401:
            return None
        logger.info("proxy: Portal upstream rejected bearer; force-refreshing invoke JWT")
        return self._get_credential(force_refresh=True, stale_access_token=failed_credential.bearer)

    def _get_credential(
        self, *, force_refresh: bool = False, stale_access_token: Optional[str] = None
    ) -> UpstreamCredential:
        with self._lock:
            state = self._read_state()
            if state is None:
                raise RuntimeError("Not logged into Arkos Portal. Run `arkos auth add portal` first.")
            try:
                refreshed = resolve_portal_runtime_credentials(
                    force_refresh=force_refresh, stale_access_token=stale_access_token or None
                )
            except Exception as exc:
                if isinstance(exc, AuthError) and _is_terminal_portal_refresh_error(exc):
                    _quarantine_portal_oauth_state(state, exc, reason="proxy_refresh_failure")
                    self._save_state(state, quarantine_error=exc, quarantine_reason="proxy_refresh_failure")
                raise RuntimeError(f"Failed to refresh Arkos Portal credentials: {exc}") from exc
            runtime_key = refreshed.get("api_key")
            if not runtime_key:
                raise RuntimeError(
                    "Arkos Portal refresh did not return a usable inference JWT. "
                    "Try `arkos auth add portal` to re-authenticate."
                )
            base_url = (
                _portal_inference_env_override()
                or _validate_portal_inference_url_from_network(refreshed.get("base_url"))
                or DEFAULT_PORTAL_INFERENCE_URL
            ).rstrip("/")
            return UpstreamCredential(bearer=runtime_key, base_url=base_url, expires_at=refreshed.get("expires_at"))


    def _read_state(self) -> Optional[Dict[str, Any]]:
        try:
            with _auth_store_lock():
                store = _load_auth_store()
        except Exception as exc:
            logger.warning("proxy: failed to load auth store: %s", exc)
            return None
        state = (store.get("providers") or {}).get("portal")
        return dict(state) if isinstance(state, dict) else None

    def _save_state(
        self,
        state: Dict[str, Any],
        *,
        quarantine_error: Optional[AuthError] = None,
        quarantine_reason: Optional[str] = None,
    ) -> None:
        try:
            with _auth_store_lock():
                store = _load_auth_store()
                if quarantine_error is not None and quarantine_reason:
                    _quarantine_portal_pool_entries(store, quarantine_error, reason=quarantine_reason)
                providers = store.setdefault("providers", {})
                providers["portal"] = state
                _save_auth_store(store)
            _write_shared_portal_state(state)
        except Exception as exc:
            logger.warning("proxy: failed to persist Portal quarantine state: %s", exc)


__all__ = ["PortalAdapter"]
