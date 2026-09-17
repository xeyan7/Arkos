"""Shared allowlist of ``/api/*`` paths that bypass dashboard auth. Imported by BOTH gates —
``web_server.auth_middleware`` (loopback / ``--insecure``) and
``dashboard_auth.middleware.gated_auth_middleware`` (OAuth cookie) — so the lists cannot drift
again (a drift once 401'd ``/api/status`` and broke the portal's cookie-less liveness probe).
Keep minimal: every entry must be safe for external uptime probes, the pre-login SPA, and anyone
who ``curl``s the hostname; otherwise gate it and bootstrap after login."""
from __future__ import annotations

PUBLIC_API_PATHS: frozenset[str] = frozenset({
    "/api/health",
    "/api/status",
    "/api/config/defaults",
    "/api/config/schema",
    "/api/model/info",
    "/api/dashboard/themes",
    "/api/dashboard/plugins",
    "/api/cron/fire"})
