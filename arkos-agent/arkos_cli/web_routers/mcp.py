"""MCP dashboard routes.

The OAuth flow registry (``_mcp_oauth_flows``) and the worker/helpers stay in
web_server — reached via the late-binding seam so tests that mutate
``web_server._mcp_oauth_flows`` or monkeypatch its helpers keep working.
"""

import asyncio
import hashlib
import re
import secrets
import threading
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from arkos_cli.web_deps import LateState, late
from arkos_cli.web_server_mcp import _mcp_oauth_flows, _mcp_server_summary, _normalize_mcp_server_create
from arkos_cli.web_models import MCPCatalogInstall, MCPEnabledToggle, MCPServerCreate, MCPServersReplace
from arkos_cli.web_routers._common import (
    _profile_cli_args, _profile_scope, _spawn_arkos_action, config_write_scope, http_failure,
    log as _log, scoped_to_thread,
)

router = APIRouter()

_config_profile_scope = late("_config_profile_scope", "arkos_cli.web_server_profiles")
_require_token = late("_require_token")
_run_dashboard_mcp_oauth = late("_run_dashboard_mcp_oauth", "arkos_cli.web_server_mcp")
load_config = late("load_config", "arkos_cli.config")
save_config = late("save_config", "arkos_cli.config")
save_env_value = late("save_env_value", "arkos_cli.config")

_mcp_oauth_flows_lock = threading.Lock()
_MCP_DASHBOARD_OAUTH_TTL = 15 * 60
_MAX_PENDING_MCP_OAUTH_FLOWS = 8


def _gc_mcp_oauth_flows() -> None:
    cutoff = time.time() - _MCP_DASHBOARD_OAUTH_TTL
    with _mcp_oauth_flows_lock:
        stale = [fid for fid, flow in _mcp_oauth_flows.items() if getattr(flow, "created_at", 0) < cutoff]
        for flow_id in stale:
            _mcp_oauth_flows.pop(flow_id, None)


def _mcp_oauth_callback_url(request: Request, server_name: str) -> str:
    """Externally reachable callback URL for a dashboard flow."""
    from urllib.parse import quote, urlparse, urlunparse

    from arkos_cli.dashboard_auth.prefix import prefix_from_request, resolve_public_url

    suffix = f"/api/mcp/oauth/callback/{quote(server_name, safe='')}"
    public_url = resolve_public_url()
    if public_url:
        return f"{public_url}{suffix}"
    base = urlparse(str(request.base_url))
    prefix = prefix_from_request(request)
    return urlunparse(base._replace(path=f"{prefix}{suffix}", params="", query="", fragment=""))


def _mcp_install_action_name(name: str) -> str:
    """Unique per-entry mcp-install action name (+ registered log file), so a
    re-click or a second catalog install doesn't overwrite the first's tracked
    process/log while its git clone is still running."""
    from arkos_cli.web_server_gateway import _ACTION_LOG_FILES
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "server"
    digest = hashlib.sha1(name.encode()).hexdigest()[:8]
    action = f"mcp-install-{slug}-{digest}"
    _ACTION_LOG_FILES.setdefault(action, f"action-{action}.log")
    return action


@router.get("/api/mcp/servers")
async def list_mcp_servers(profile: Optional[str] = None):
    from arkos_cli.mcp_config import _get_mcp_servers

    servers = await scoped_to_thread(profile, _get_mcp_servers)
    return {"servers": [_mcp_server_summary(name, cfg) for name, cfg in sorted(servers.items())]}


@router.post("/api/mcp/servers")
async def add_mcp_server(body: MCPServerCreate, profile: Optional[str] = None):
    from arkos_cli.mcp_config import _get_mcp_servers, _save_bearer_auth_token, _save_mcp_server

    try:
        name, server_config, bearer_token = _normalize_mcp_server_create(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    def _run():
        with config_write_scope(body.profile or profile):
            if name in _get_mcp_servers():
                raise HTTPException(status_code=409, detail=f"Server '{name}' already exists")
            if bearer_token is not None:
                server_config["headers"] = _save_bearer_auth_token(name, bearer_token)
            if not _save_mcp_server(name, server_config):
                raise HTTPException(
                    status_code=400, detail=f"Server '{name}' rejected: suspicious command/args configuration",
                )

    try:
        await asyncio.to_thread(_run)
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("POST /api/mcp/servers failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _mcp_server_summary(name, server_config)


@router.put("/api/mcp/servers")
async def replace_mcp_servers(body: MCPServersReplace, profile: Optional[str] = None):
    """Replace the entire ``mcp_servers`` map (the mcp.json editor's save) —
    the deep-merging ``/api/config`` can never delete a key or drop an
    ``enabled: false``, so removals wouldn't persist through it."""
    from arkos_cli.mcp_config import _replace_mcp_servers

    def _run():
        with config_write_scope(body.profile or profile):
            return _replace_mcp_servers(body.servers)

    ok, issues = await asyncio.to_thread(_run)
    if not ok:
        raise HTTPException(status_code=400, detail="; ".join(issues))
    return {"ok": True}


@router.delete("/api/mcp/servers/{name}")
async def remove_mcp_server(name: str, profile: Optional[str] = None):
    from arkos_cli.mcp_config import _remove_mcp_server

    def _run():
        with config_write_scope(profile):
            return _remove_mcp_server(name)

    if not await asyncio.to_thread(_run):
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    return {"ok": True}


@router.post("/api/mcp/servers/{name}/test")
async def test_mcp_server(name: str, profile: Optional[str] = None):
    """Connect to the server, list its tools, disconnect."""
    from arkos_cli.mcp_config import _get_mcp_servers, _oauth_tokens_present, _probe_single_server

    servers = await scoped_to_thread(profile, _get_mcp_servers)
    if name not in servers:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")

    details: Dict[str, Any] = {}
    needs_oauth_token = servers[name].get("auth") == "oauth"

    def _probe_scoped():
        with _config_profile_scope(profile):
            tools = _probe_single_server(name, servers[name], details=details)
            return tools, (_oauth_tokens_present(name) if needs_oauth_token else True)

    try:
        tools, token_present = await asyncio.to_thread(_probe_scoped)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tools": []}
    if not token_present:
        return {"ok": False, "error": "OAuth authentication required — no token found.", "tools": []}
    schema_chars = details.get("schema_chars") or {}
    return {
        "ok": True,
        "tools": [
            {
                "name": t,
                "description": d,
                **({"schema_chars": schema_chars[t]} if isinstance(schema_chars.get(t), int) else {}),
            }
            for t, d in tools
        ],
        "prompts": details.get("prompts", 0),
        "resources": details.get("resources", 0),
    }


@router.post("/api/mcp/servers/{name}/auth")
async def auth_mcp_server(name: str, request: Request, profile: Optional[str] = None):
    """Start MCP OAuth and hand the authorization URL to the dashboard browser."""
    from arkos_cli.mcp_config import _get_mcp_servers
    from arkos_constants import get_arkos_home
    from tools.mcp_dashboard_oauth import DashboardOAuthFlow

    _require_token(request)
    _gc_mcp_oauth_flows()

    def _home() -> str:
        return str(get_arkos_home().expanduser().resolve(strict=False))

    process_home = _home()

    def _read():
        with _profile_scope(profile):
            return _get_mcp_servers(), _home()

    servers, flow_home = await asyncio.to_thread(_read)
    if name not in servers:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    cfg = dict(servers[name])
    if not cfg.get("url"):
        raise HTTPException(status_code=400, detail="stdio servers authenticate via env keys, not OAuth")
    if cfg.get("headers") and cfg.get("auth") != "oauth":
        raise HTTPException(status_code=400, detail="This server uses header/API-key auth, not OAuth")
    cfg["auth"] = "oauth"

    flow_id = secrets.token_urlsafe(24)
    flow = DashboardOAuthFlow(
        flow_id=flow_id,
        server_name=name,
        profile=profile,
        arkos_home=flow_home,
        redirect_uri=(cfg.get("oauth") or {}).get("redirect_uri") or _mcp_oauth_callback_url(request, name),
        reconnect_live=flow_home == process_home,
    )
    with _mcp_oauth_flows_lock:
        live = [f for f in _mcp_oauth_flows.values() if not f.worker_done]
        if len(live) >= _MAX_PENDING_MCP_OAUTH_FLOWS:
            raise HTTPException(status_code=429, detail="Too many MCP OAuth flows are already in progress")
        if any(f.server_name == name and f.arkos_home == flow_home for f in live):
            raise HTTPException(status_code=409, detail=f"MCP OAuth for '{name}' is already in progress")
        _mcp_oauth_flows[flow_id] = flow
    threading.Thread(target=_run_dashboard_mcp_oauth, args=(flow, cfg), daemon=True, name=f"mcp-oauth-{name}").start()
    try:
        await flow.wait_for_authorization_url(timeout=30)
    except Exception as exc:
        flow.mark_error(str(exc))
    return flow.snapshot()


@router.get("/api/mcp/oauth/flows/{flow_id}")
async def mcp_oauth_flow_status(flow_id: str, request: Request):
    _require_token(request)
    _gc_mcp_oauth_flows()
    flow = _mcp_oauth_flows.get(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="OAuth flow not found or expired")
    snapshot = flow.snapshot()
    snapshot["tools"] = flow.tools
    return snapshot


@router.delete("/api/mcp/oauth/flows/{flow_id}")
async def cancel_mcp_oauth_flow(flow_id: str, request: Request):
    """Cancel an in-flight flow. mark_error unblocks the worker so it frees the
    per-server "already in progress" slot — otherwise a renderer that stops
    polling leaves the flow squatting until the 300s callback timeout and every
    retry 409s. Idempotent: a settled flow is left as-is."""
    _require_token(request)
    flow = _mcp_oauth_flows.get(flow_id)
    if flow is None:
        return {"ok": True, "status": "expired"}
    flow.mark_error("Cancelled by user")
    return {"ok": True, "status": flow.snapshot()["status"]}


@router.get("/api/mcp/oauth/callback/{server_name:path}")
async def mcp_oauth_callback(
    server_name: str,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    _gc_mcp_oauth_flows()
    with _mcp_oauth_flows_lock:
        candidates = [
            flow for flow in _mcp_oauth_flows.values()
            if flow.server_name == server_name and flow.status == "authorization_required"
        ]
    flow = next(
        (c for c in candidates
         if c.expected_state is not None and state is not None and secrets.compare_digest(c.expected_state, state)),
        None,
    )
    if flow is None:
        return HTMLResponse("<h1>OAuth flow expired</h1><p>Return to Arkos and try again.</p>", status_code=404)
    try:
        flow.deliver_callback(code=code, state=state, error=error)
    except ValueError as exc:
        return HTMLResponse(
            "<h1>OAuth callback rejected</h1><p>The callback was invalid or already used.</p>",
            status_code=409 if "already received" in str(exc) else 400,
        )
    if error:
        return HTMLResponse("<h1>Authorization failed</h1><p>Return to Arkos for details.</p>", status_code=400)
    return HTMLResponse("<h1>Authorization received</h1><p>You can close this tab and return to Arkos.</p>")


@router.put("/api/mcp/servers/{name}/enabled")
async def set_mcp_server_enabled(name: str, body: MCPEnabledToggle, profile: Optional[str] = None):
    """Toggle ``enabled`` (takes effect on next session/gateway); disabled
    servers stay in config so they can be re-enabled without re-entry."""
    def _run():
        with config_write_scope(body.profile or profile):
            cfg = load_config()
            servers = cfg.get("mcp_servers")
            if not isinstance(servers, dict) or name not in servers:
                raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
            if not isinstance(servers[name], dict):
                raise HTTPException(status_code=400, detail="Malformed server config")
            servers[name]["enabled"] = bool(body.enabled)
            save_config(cfg)
        return {"ok": True, "name": name, "enabled": bool(body.enabled)}

    return await asyncio.to_thread(_run)


def _catalog_entry_json(entry: Any, installed: bool, enabled: bool) -> Dict[str, Any]:
    auth = entry.auth
    transport = entry.transport
    install = entry.install
    return {
        "name": entry.name,
        "description": entry.description,
        "source": entry.source,
        "transport": transport.type,
        "auth_type": getattr(auth, "type", "none"),
        "required_env": [
            {"name": e.name, "prompt": e.prompt, "required": e.required}
            for e in getattr(auth, "env", []) or []
        ],
        "command": transport.command,
        "args": list(transport.args or []),
        "url": transport.url,
        "install_url": install.url if install else None,
        "install_ref": install.ref if install else None,
        "bootstrap": list(install.bootstrap) if install else [],
        "default_enabled": list(entry.tools.default_enabled) if entry.tools.default_enabled is not None else None,
        "post_install": entry.post_install or "",
        "suggest": {"keywords": list(entry.suggest.keywords), "hosts": list(entry.suggest.hosts)} if entry.suggest else None,
        "needs_install": install is not None,
        "installed": installed,
        "enabled": enabled,
    }


@router.get("/api/mcp/catalog")
async def list_mcp_catalog(profile: Optional[str] = None):
    """Browse the Portal-approved MCP catalog (optional-mcps/ manifests), each
    entry annotated with installed/enabled state for ``profile``."""
    with http_failure("mcp_catalog import failed", 500, "Catalog unavailable"):
        from arkos_cli import mcp_catalog

    entries = []
    try:
        def _read():
            with _profile_scope(profile):
                catalog = list(mcp_catalog.list_catalog())
                state = {e.name: (mcp_catalog.is_installed(e.name), mcp_catalog.is_enabled(e.name)) for e in catalog}
            return catalog, state

        catalog_entries, installed_state = await asyncio.to_thread(_read)
        for entry in catalog_entries:
            installed, enabled = installed_state.get(entry.name, (False, False))
            entries.append(_catalog_entry_json(entry, installed, enabled))
    except HTTPException:
        raise
    except Exception:
        _log.exception("list_mcp_catalog failed")

    diagnostics = []
    try:
        diagnostics = [{"name": n, "kind": k, "message": m} for (n, k, m) in mcp_catalog.catalog_diagnostics()]
    except Exception:
        pass
    return {"entries": entries, "diagnostics": diagnostics}


@router.post("/api/mcp/catalog/install")
async def install_mcp_catalog_entry(body: MCPCatalogInstall, profile: Optional[str] = None):
    """Install a catalog MCP into config.yaml (declared env vars go to .env
    first; git-bootstrap entries run via the background CLI action path)."""
    from arkos_cli import mcp_catalog
    from arkos_cli.config import validate_env_var_name_for_write

    name = (body.name or "").strip()
    entry = mcp_catalog.get_entry(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No catalog entry '{name}'")

    declared_env = {spec.name for spec in (entry.auth.env or [])}
    undeclared_env = sorted(set(body.env) - declared_env)
    if undeclared_env:
        raise HTTPException(
            status_code=400,
            detail=f"Catalog entry '{name}' does not declare environment variable(s): {', '.join(undeclared_env)}",
        )
    try:
        for key in body.env:
            validate_env_var_name_for_write(key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    effective_profile = body.profile or profile
    if body.env:
        def _write_env():
            with _profile_scope(effective_profile):
                for k, v in body.env.items():
                    if v:
                        save_env_value(k, v)

        await asyncio.to_thread(_write_env)

    if entry.install is not None:
        action = _mcp_install_action_name(name)
        try:
            _spawn_arkos_action(_profile_cli_args(effective_profile) + ["mcp", "install", name], action)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Install failed: {exc}")
        return {"ok": True, "name": name, "background": True, "action": action}

    try:
        await scoped_to_thread(effective_profile, lambda: mcp_catalog.install_entry(entry, enable=body.enable))
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("install_mcp_catalog_entry failed")
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "name": name, "background": False}


import logging  # noqa: F401,E402
