"""Browser Use cloud browser backend using BROWSER_USE_API_KEY."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests

from agent.secret_scope import get_secret
from plugins.browser._common import CloudBrowserProvider

logger = logging.getLogger(__name__)


_BASE_URL = "https://api.browser-use.com/api/v3"


class BrowserUseBrowserProvider(CloudBrowserProvider):
    """Browser Use (https://browser-use.com) cloud browser backend."""

    provider_id = "browser-use"
    label = "Browser Use"
    release_method = "patch"
    release_path = "/browsers/{session_id}"
    setup_tag = None

    def is_available(self) -> bool:
        return self._get_config_or_none(refresh_token=False) is not None

    def _get_config_or_none(self, *, refresh_token: bool = True) -> Optional[Dict[str, Any]]:
        key = get_secret("BROWSER_USE_API_KEY")
        return {"api_key": key, "base_url": _BASE_URL} if key else None

    def _get_config(self) -> Dict[str, Any]:
        config = self._get_config_or_none()
        if config is None:
            raise ValueError("Browser Use requires BROWSER_USE_API_KEY")
        return config

    def _headers(self, config: Dict[str, Any]) -> Dict[str, str]:
        return {"Content-Type": "application/json", "X-Browser-Use-API-Key": config["api_key"]}

    def _release_body(self, config: Dict[str, Any]) -> Dict[str, object]:
        return {"action": "stop"}

    def create_session(self, task_id: str) -> Dict[str, object]:
        config = self._get_config()

        headers = self._headers(config)
        response = self._post_create(
            f"{config['base_url']}/browsers", headers, {}, wrap_errors=True)
        self._check_created(response)

        session_data = response.json()
        session_name = self._session_name(task_id)
        logger.info("Created Browser Use session %s", session_name)
        return {
            "session_name": session_name,
            "bb_session_id": session_data["id"],
            "cdp_url": session_data.get("cdpUrl") or session_data.get("connectUrl") or "",
            "expires_at": session_data.get("timeoutAt"),
            "features": {"browser_use": True},
        }


import os  # noqa: F401,E402
