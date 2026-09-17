"""Arkos Portal OAuth: device-code login, refresh, shared-store mirroring, JWT selection, status.

Split out of ``arkos_cli/auth.py``; origin helpers are imported lazily inside each function
so ``arkos_cli.auth.<name>`` patches still intercept (and no import cycle).
"""

from __future__ import annotations

import logging
import hashlib
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, FrozenSet, List, Optional
from urllib.parse import urlparse
from arkos_cli.auth_codex import _pool_entries
from arkos_cli.auth_constants import (
    _decode_jwt_claims, AUTH_LOCK_TIMEOUT_SECONDS, AuthError, DEFAULT_PORTAL_CLIENT_ID,
    DEFAULT_PORTAL_INFERENCE_URL, DEFAULT_PORTAL_URL, DEFAULT_PORTAL_SCOPE,
    DEVICE_AUTH_POLL_INTERVAL_CAP_SECONDS, PORTAL_AUTH_PATH_INVOKE_JWT, PORTAL_BILLING_MANAGE_SCOPE,
    PORTAL_DEVICE_CODE_SOURCE, PORTAL_INFERENCE_INVOKE_SCOPE, PORTAL_INVOKE_JWT_MIN_TTL_SECONDS,
    _portal_err, httpx)

if TYPE_CHECKING:
    from arkos_cli.auth import ProviderConfig

logger = logging.getLogger("arkos_cli.auth")

_UNUSABLE_JWT_RELOGIN = "Re-authenticate with: arkos auth add portal"


def _unusable_invoke_jwt_error(reason: str, *, no_refresh_token: bool = False) -> AuthError:
    """Shared ``relogin=True`` error for an access token that is not a usable inference JWT."""
    detail = " and no refresh token is available" if no_refresh_token else ""
    return _portal_err(
        f"Arkos Portal access token is not a usable inference JWT ({reason}){detail}. "
        f"{_UNUSABLE_JWT_RELOGIN}",
        reason, relogin=True)


def _token_fingerprint(token: Any) -> Optional[str]:
    """Return a short hash fingerprint for telemetry without leaking token bytes."""
    cleaned = token.strip() if isinstance(token, str) else ""
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:12] if cleaned else None


def _oauth_trace(event: str, *, sequence_id: Optional[str] = None, **fields: Any) -> None:
    if os.getenv("ARKOS_OAUTH_TRACE", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return
    payload: Dict[str, Any] = {"event": event}
    if sequence_id:
        payload["sequence_id"] = sequence_id
    payload.update(fields)
    logger.info("oauth_trace %s", json.dumps(payload, sort_keys=True, ensure_ascii=False))


def _iso_after(now: datetime, ttl_seconds: int) -> str:
    """ISO timestamp *ttl_seconds* after *now* (UTC)."""
    return datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=timezone.utc).isoformat()


_PORTAL_EMPTY_AGENT_KEY_FIELDS: Dict[str, Any] = {
    "agent_key": None, "agent_key_id": None, "agent_key_expires_at": None,
    "agent_key_expires_in": None, "agent_key_reused": None, "agent_key_obtained_at": None}

_PORTAL_STALE_HOSTS: FrozenSet[str] = frozenset()


def _portal_entitlement_message(capability: str) -> str:
    """Portal entitlement notice for *capability* (fresh account data), "" when unavailable."""
    return ""


def _format_portal_entitlement_auth_error(error: AuthError) -> str:
    return str(error)


def _migrate_stale_portal_url(providers: Dict[str, Any]) -> None:
    pass


_ALLOWED_PORTAL_INFERENCE_HOSTS: FrozenSet[str] = frozenset()


def _validate_portal_inference_url_from_network(url: Optional[str]) -> Optional[str]:
    """Validate a Portal-returned inference URL against the host allowlist.

    Defense-in-depth: a compromised refresh response (MITM, response injection) could otherwise
    redirect every proxy request — bearing the user's inference JWT — to an attacker endpoint.
    """
    cleaned = url.strip() if isinstance(url, str) else ""
    if not cleaned:
        return None
    try:
        parsed = urlparse(cleaned)
    except Exception:
        return None
    if parsed.scheme != "https":
        logger.warning(
            "portal: refusing non-https inference URL scheme %r from Portal response", parsed.scheme)
        return None
    if parsed.hostname not in _ALLOWED_PORTAL_INFERENCE_HOSTS:
        logger.warning(
            "portal: refusing inference URL host %r from Portal response "
            "(not in allowlist); falling back to default",
            parsed.hostname)
        return None
    return cleaned.rstrip("/")


def _portal_inference_env_override() -> Optional[str]:
    """User-set ``PORTAL_INFERENCE_BASE_URL`` override (trailing slash stripped) or None.

    Documented dev/staging escape hatch; the env source is trusted, so unlike Portal-returned URLs
    it is intentionally NOT gated by the network host allowlist.
    """
    from arkos_cli.auth import _optional_base_url
    return _optional_base_url(os.getenv("PORTAL_INFERENCE_BASE_URL"))


def _portal_env_override() -> Optional[str]:
    """``ARKOS_PORTAL_BASE_URL`` / ``PORTAL_BASE_URL`` override or None.

    Documented dev/staging escape hatch (e.g. hosted agents on the staging Portal). Trusted env
    source: must NOT be gated by ``_PORTAL_ALLOWED_HOSTS``, which rejects untrusted
    NETWORK-provided values persisted to auth.json, not operator config.
    """
    from arkos_cli.auth import _optional_base_url
    return _optional_base_url(
        os.getenv("ARKOS_PORTAL_BASE_URL") or os.getenv("PORTAL_BASE_URL"))


def _scope_values(raw_scope: Any) -> set[str]:
    scopes: set[str] = set()
    if isinstance(raw_scope, str):
        scopes.update(part for part in raw_scope.replace(",", " ").split() if part.strip())
    elif isinstance(raw_scope, (list, tuple, set, frozenset)):
        scopes.update(*(_scope_values(item) for item in raw_scope if isinstance(item, str)))
    return scopes


def _portal_invoke_jwt_status(
    token: Any, *, scope: Any = None, expires_at: Any = None,
    min_ttl_seconds: int = PORTAL_INVOKE_JWT_MIN_TTL_SECONDS) -> Optional[str]:
    """Return None when the token can be used for inference, else a reason."""
    from arkos_cli.auth import _is_expiring
    claims = _decode_jwt_claims(token)
    if not claims:
        return "access_token_not_jwt"
    scopes = (_scope_values(scope) | _scope_values(claims.get("scope"))
              | _scope_values(claims.get("scp")))
    if PORTAL_INFERENCE_INVOKE_SCOPE not in scopes:
        return "missing_inference_invoke_scope"
    exp = claims.get("exp")
    skew = max(0, int(min_ttl_seconds))
    if isinstance(exp, (int, float)):
        return "invoke_jwt_expiring" if float(exp) <= (time.time() + skew) else None
    return "invoke_jwt_expiry_unknown_or_expiring" if _is_expiring(expires_at, skew) else None


def _portal_invoke_jwt_is_usable(
    token: Any, *, scope: Any = None, expires_at: Any = None,
    min_ttl_seconds: int = PORTAL_INVOKE_JWT_MIN_TTL_SECONDS) -> bool:
    from arkos_cli.auth import _portal_invoke_jwt_status
    return _portal_invoke_jwt_status(
        token, scope=scope, expires_at=expires_at, min_ttl_seconds=min_ttl_seconds) is None


def _state_invoke_jwt_status(state: Dict[str, Any], token: Any) -> Optional[str]:
    """``_portal_invoke_jwt_status`` for *token* using *state*'s scope / expires_at (patchable)."""
    from arkos_cli.auth import _portal_invoke_jwt_status
    return _portal_invoke_jwt_status(
        token, scope=state.get("scope"), expires_at=state.get("expires_at"))


def _assert_portal_inference_jwt_usable(state: Dict[str, Any], *, access_token: Any = None) -> None:
    token = state.get("access_token") if access_token is None else access_token
    reason = _state_invoke_jwt_status(state, token)
    if reason is not None:
        raise _unusable_invoke_jwt_error(reason)


def _remaining_ttl(expires_at: Any, fallback_expires_in: Any) -> int:
    """Seconds until *expires_at* (ISO), else *fallback_expires_in* coerced to a TTL."""
    from arkos_cli.auth import _coerce_ttl_seconds, _parse_iso_timestamp
    expires_epoch = _parse_iso_timestamp(expires_at)
    if expires_epoch is not None:
        return max(0, int(expires_epoch - time.time()))
    return _coerce_ttl_seconds(fallback_expires_in)


def _portal_jwt_expires_at(token: Any, fallback_expires_at: Any = None) -> Optional[str]:
    claims = _decode_jwt_claims(token)
    exp = claims.get("exp")
    if isinstance(exp, (int, float)):
        with suppress(Exception):
            return datetime.fromtimestamp(float(exp), tz=timezone.utc).isoformat()
    return fallback_expires_at if isinstance(fallback_expires_at, str) else None


def _set_portal_agent_key_from_invoke_jwt(
    state: Dict[str, Any], *, obtained_at: Optional[str] = None) -> None:
    from arkos_cli.auth import _nonempty_str
    access_token = state.get("access_token")
    if not _nonempty_str(access_token):
        return
    existing_obtained_at = state.get("agent_key_obtained_at")
    if not obtained_at:
        reuse = state.get("agent_key") == access_token and _nonempty_str(existing_obtained_at)
        obtained_at = existing_obtained_at if reuse else datetime.now(timezone.utc).isoformat()
    expires_at = _portal_jwt_expires_at(access_token, state.get("expires_at"))
    expires_in = _remaining_ttl(expires_at, state.get("expires_in"))
    if expires_at:
        state["expires_at"] = expires_at
        state["expires_in"] = expires_in
    state.update(
        agent_key=access_token, agent_key_id=None, agent_key_expires_at=expires_at,
        agent_key_expires_in=expires_in, agent_key_reused=False, agent_key_obtained_at=obtained_at)


def _select_portal_invoke_jwt(
    state: Dict[str, Any], *, access_token: Any = None, sequence_id: Optional[str] = None) -> None:
    from arkos_cli.auth import _nonempty_str
    if _nonempty_str(access_token):
        state["access_token"] = access_token
    _set_portal_agent_key_from_invoke_jwt(state)
    logger.debug("Portal inference auth: using Portal invoke JWT")
    _oauth_trace(
        "portal_invoke_jwt_selected", sequence_id=sequence_id,
        access_token_fp=_token_fingerprint(state.get("access_token")))


_PORTAL_EFFECTIVE_STATE_IGNORED_KEYS = frozenset({"expires_in", "agent_key_expires_in"})


def _portal_effective_provider_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in state.items() if k not in _PORTAL_EFFECTIVE_STATE_IGNORED_KEYS}


PORTAL_SHARED_STORE_FILENAME = "portal_auth.json"
_portal_shared_lock_holder = threading.local()


def _portal_shared_auth_dir() -> Path:
    """Directory of the shared Portal token store: ``ARKOS_SHARED_AUTH_DIR`` or ``<root>/shared/``.

    Outside any named profile so all profiles share it (``arkos --profile X auth add portal --type
    oauth`` one-tap imports it). Written on login AND every runtime refresh so the refresh_token
    stays current across profiles; a stale token just falls back to device-code.
    """
    override = os.getenv("ARKOS_SHARED_AUTH_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    from arkos_constants import get_default_arkos_root
    return get_default_arkos_root() / "shared"


def _portal_shared_store_path() -> Path:
    path = _portal_shared_auth_dir() / PORTAL_SHARED_STORE_FILENAME
    if os.environ.get("PYTEST_CURRENT_TEST"):
        from arkos_constants import get_default_arkos_root
        real_home_shared = (
            get_default_arkos_root() / "shared" / PORTAL_SHARED_STORE_FILENAME).resolve(strict=False)
        try:
            resolved = path.resolve(strict=False)
        except Exception:
            resolved = path
        if resolved == real_home_shared:
            raise RuntimeError(
                f"Refusing to touch real user shared Portal auth store during test run: "
                f"{path}. Set ARKOS_SHARED_AUTH_DIR to a tmp_path in your test fixture.")
    return path


@contextmanager
def _portal_shared_store_lock(timeout_seconds: float = AUTH_LOCK_TIMEOUT_SECONDS):
    """Cross-profile lock for the shared Portal OAuth store.

    Lock ordering invariant: if both this and ``_auth_store_lock`` need to be held, acquire
    ``_auth_store_lock`` FIRST. All runtime refresh paths follow this order.
    """
    from arkos_cli.auth import _file_lock
    try:
        lock_path = _portal_shared_store_path().with_suffix(".lock")
    except RuntimeError:
        yield
        return
    with _file_lock(
        lock_path, _portal_shared_lock_holder, timeout_seconds,
        "Timed out waiting for shared Portal auth lock"):
        yield


def _shared_lock_timeout(timeout_seconds: float) -> float:
    return max(timeout_seconds + 5.0, AUTH_LOCK_TIMEOUT_SECONDS)


_PORTAL_SHARED_STATE_KEYS = (
    "access_token", "refresh_token", "token_type", "scope", "client_id", "portal_base_url",
    "inference_base_url", "obtained_at", "expires_at")


def _merge_shared_portal_oauth_state(state: Dict[str, Any]) -> bool:
    """Copy fresher shared OAuth tokens into a profile-local Portal state."""
    from arkos_cli.auth import _nonempty_str, _parse_iso_timestamp, _read_shared_portal_state
    shared = _read_shared_portal_state() or {}
    shared_refresh = shared.get("refresh_token")
    if not _nonempty_str(shared_refresh):
        return False
    shared_access_exp = _parse_iso_timestamp(shared.get("expires_at")) or 0.0
    local_access_exp = _parse_iso_timestamp(state.get("expires_at")) or 0.0
    refresh_changed = shared_refresh.strip() != str(state.get("refresh_token") or "").strip()
    if not refresh_changed and not shared_access_exp > local_access_exp:
        return False
    for key in _PORTAL_SHARED_STATE_KEYS:
        value = shared.get(key)
        if value not in {None, ""}:
            state[key] = value
    return True


def _portal_shared_shape(src: Dict[str, Any]) -> Dict[str, Any]:
    """The defaulted OAuth core (tokens + routing + expiry) shared across profiles."""
    return {
        "access_token": src.get("access_token"), "refresh_token": src.get("refresh_token"),
        "token_type": src.get("token_type") or "Bearer",
        "scope": src.get("scope") or DEFAULT_PORTAL_SCOPE,
        "client_id": src.get("client_id") or DEFAULT_PORTAL_CLIENT_ID,
        "portal_base_url": src.get("portal_base_url") or DEFAULT_PORTAL_URL,
        "inference_base_url": src.get("inference_base_url") or DEFAULT_PORTAL_INFERENCE_URL,
        "obtained_at": src.get("obtained_at"), "expires_at": src.get("expires_at")}


def _write_shared_portal_state(state: Dict[str, Any]) -> None:
    """Persist a minimal copy of the Portal OAuth state to the shared store.

    Best-effort: failures are logged and swallowed; per-profile auth.json stays the source of truth.
    """
    from arkos_cli.auth import _nonempty_str, _write_private_file_atomic
    refresh_token = state.get("refresh_token")
    if not (_nonempty_str(refresh_token) and _nonempty_str(state.get("access_token"))):
        return
    shared = {
        "_schema": 1, **_portal_shared_shape(state),
        "updated_at": datetime.now(timezone.utc).isoformat()}
    try:
        with _portal_shared_store_lock():
            path = _portal_shared_store_path()
            _write_private_file_atomic(
                path, json.dumps(shared, indent=2, sort_keys=True), replace=os.replace)
        _oauth_trace(
            "portal_shared_store_written", path=str(path),
            refresh_token_fp=_token_fingerprint(refresh_token))
    except Exception as exc:
        logger.debug("Failed to write shared Portal auth store: %s", exc)


def _read_shared_portal_state() -> Optional[Dict[str, Any]]:
    """Shared Portal OAuth state when present and well-formed, else None.

    None (missing / unreadable / malformed / lacking tokens) means "fall through to device-code".
    """
    from arkos_cli.auth import _nonempty_str
    try:
        path = _portal_shared_store_path()
    except RuntimeError:
        return None
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        logger.debug("Shared Portal auth store at %s is unreadable: %s", path, exc)
        return None
    if not isinstance(payload, dict):
        return None
    has_tokens = (
        _nonempty_str(payload.get("refresh_token")) and _nonempty_str(payload.get("access_token")))
    return payload if has_tokens else None


def _clear_shared_portal_state(reason: str) -> None:
    """Remove the shared Portal OAuth store after a terminal token failure."""
    try:
        with _portal_shared_store_lock():
            _portal_shared_store_path().unlink(missing_ok=True)
        _oauth_trace("portal_shared_store_cleared", reason=reason)
    except Exception as exc:
        logger.debug("Failed to clear shared Portal auth store: %s", exc)


def _quarantine_forensics(state: Dict[str, Any], error: AuthError, reason: str) -> Dict[str, Any]:
    """Redaction-safe forensic record for a quarantine: fingerprints, sizes and booleans only.

    NEVER include a raw token/agent_key (credential-shaped literals get corrupted in logs). The
    12-char SHA-256 prefix correlates to Portal's refreshTokenHash without leaking the secret;
    provenance is client_id + agent_key_id (Portal state has no session_id).
    """
    from arkos_cli.auth import _auth_file_path
    forensic: Dict[str, Any] = {
        "reason": reason, "error_code": error.code, "client_id": state.get("client_id"),
        "agent_key_id": state.get("agent_key_id"),
        "refresh_token_fp": _token_fingerprint(state.get("refresh_token"))}
    try:
        auth_path = _auth_file_path()
        forensic["auth_json_path"] = str(auth_path)
        try:
            st = os.stat(auth_path)
            forensic.update(
                auth_json_size=st.st_size, auth_json_mtime=st.st_mtime, auth_json_exists=True)
        except FileNotFoundError:
            forensic["auth_json_exists"] = False
    except Exception as exc:  # pragma: no cover - never let logging break quarantine
        forensic["auth_json_stat_error"] = repr(exc)
    already_expired: Optional[bool] = None
    expires_at_raw = state.get("expires_at")
    if isinstance(expires_at_raw, str) and expires_at_raw:
        try:
            parsed = datetime.fromisoformat(expires_at_raw)
            already_expired = (parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
                               < datetime.now(timezone.utc))
        except ValueError:
            already_expired = None
    forensic["token_already_expired"] = already_expired
    return forensic


def _quarantine_portal_oauth_state(state: Dict[str, Any], error: AuthError, *, reason: str) -> None:
    """Keep routing metadata but remove dead OAuth material so it is not replayed.

    Only for terminal errors (``*_refresh_failed`` = HTTP 400/401/403 invalid_grant / revoked /
    refresh_token_reused; ``*_auth_missing_refresh_token``), all ``relogin_required=True`` —
    transient 429/5xx never quarantine.
    """
    from arkos_cli.auth import (
        _FLAT_OAUTH_TOKEN_KEYS, _last_auth_error_marker, invalidate_portal_auth_status_cache)
    logger.warning(
        "Portal OAuth state quarantined (terminal auth death): %s",
        json.dumps(_quarantine_forensics(state, error, reason), sort_keys=True, ensure_ascii=False))
    for key in (*_FLAT_OAUTH_TOKEN_KEYS, *_PORTAL_EMPTY_AGENT_KEY_FIELDS):
        state.pop(key, None)
    state["last_auth_error"] = _last_auth_error_marker("portal", error, reason=reason)
    _clear_shared_portal_state(reason)
    invalidate_portal_auth_status_cache()


def _quarantine_portal_pool_entries(
    auth_store: Dict[str, Any], error: AuthError, *, reason: str) -> bool:
    """Remove singleton-seeded Portal pool entries that contain dead OAuth state."""
    entries = _pool_entries(auth_store, "portal")
    if entries is None:
        return False
    singleton_sources = {PORTAL_DEVICE_CODE_SOURCE, f"manual:{PORTAL_DEVICE_CODE_SOURCE}"}
    retained = [
        e for e in entries if not (isinstance(e, dict) and e.get("source") in singleton_sources)]
    removed = len(retained) != len(entries)
    if removed:
        auth_store["credential_pool"]["portal"] = retained
        _oauth_trace("portal_pool_device_code_quarantined", reason=reason, error_code=error.code)
    return removed


def _try_import_shared_portal_state(*, timeout_seconds: float = 15.0) -> Optional[Dict[str, Any]]:
    """Rehydrate Portal OAuth state from the shared store via a forced refresh.

    Returns auth_state ready for ``persist_portal_credentials()``; None on any failure (expired
    token, portal unreachable) so the caller falls through to device-code.
    """
    from arkos_cli.auth import (
        _read_shared_portal_state, _write_shared_portal_state, refresh_portal_oauth_from_state,
        _is_terminal_portal_refresh_error)
    try:
        with _portal_shared_store_lock(timeout_seconds=_shared_lock_timeout(timeout_seconds)):
            shared = _read_shared_portal_state()
            if not shared:
                return None
            state: Dict[str, Any] = {
                **_portal_shared_shape(shared), "agent_key": None, "agent_key_expires_at": None,
                "tls": {"insecure": False, "ca_bundle": None}}
            refreshed = refresh_portal_oauth_from_state(
                state, timeout_seconds=timeout_seconds, force_refresh=True,
                on_state_update=lambda updated, _reason: _write_shared_portal_state(updated))
            _write_shared_portal_state(refreshed)
    except Exception as exc:
        is_auth = isinstance(exc, AuthError)
        _oauth_trace(
            "portal_shared_import_failed", error_type=type(exc).__name__,
            **({"error_code": getattr(exc, "code", None)} if is_auth else {}))
        if is_auth and _is_terminal_portal_refresh_error(exc):
            _clear_shared_portal_state("shared_import_terminal_refresh_failure")
        logger.debug("Shared Portal import failed: %s", exc)
        return None
    return refreshed


def _refresh_access_token(
    *, client: httpx.Client, portal_base_url: str, client_id: str, refresh_token: str,
) -> Dict[str, Any]:
    response = client.post(
        f"{portal_base_url}/api/oauth/token",
        headers={"x-portal-refresh-token": refresh_token},
        data={"grant_type": "refresh_token", "client_id": client_id})
    if response.status_code == 200:
        payload = response.json()
        if "access_token" not in payload:
            raise _portal_err("Refresh response missing access_token", "invalid_token", relogin=True)
        return payload
    try:
        error_payload = response.json()
    except Exception as exc:
        raise _portal_err("Refresh token exchange failed", relogin=True) from exc
    code = str(error_payload.get("error", "invalid_grant"))
    description = str(error_payload.get("error_description") or "Refresh token exchange failed")
    relogin = code in {"invalid_grant", "invalid_token", "refresh_token_reused"}
    if code == "refresh_token_reused" or "reuse" in description.lower():
        description = (
            "Arkos Portal detected refresh-token reuse and revoked this session.\n"
            "This usually means an external process (monitoring script, "
            "custom self-heal hook, or another Arkos install sharing "
            "~/.arkos/auth.json) called POST /api/oauth/token with Arkos's "
            "refresh token without persisting the rotated token back.\n"
            "Portal refresh tokens are single-use — only Arkos may call the "
            "refresh endpoint. For health checks, use `arkos auth status` "
            "instead.\n"
            "Re-authenticate with: arkos auth add portal")
        relogin = True
    raise _portal_err(description, code, relogin=relogin)


def _refresh_portal_or_quarantine(
    *, client: httpx.Client, auth_store: Dict[str, Any], state: Dict[str, Any],
    portal_base_url: str, client_id: str, refresh_token: str, reason: str,
    persist: Callable[[], None]) -> Dict[str, Any]:
    """Redeem the refresh token; on terminal failure quarantine state + pool, persist, re-raise."""
    from arkos_cli.auth import _refresh_access_token, _is_terminal_portal_refresh_error
    try:
        return _refresh_access_token(
            client=client, portal_base_url=portal_base_url, client_id=client_id,
            refresh_token=refresh_token)
    except AuthError as exc:
        if _is_terminal_portal_refresh_error(exc):
            _quarantine_portal_oauth_state(state, exc, reason=reason)
            _quarantine_portal_pool_entries(auth_store, exc, reason=reason)
            persist()
        raise


def _apply_portal_refreshed_tokens(
    state: Dict[str, Any], refreshed: Dict[str, Any], refresh_token: str, *,
    inference_base_url: Optional[str] = None) -> None:
    """Write a successful Portal token-refresh payload into *state* (tokens + expiry fields).

    *inference_base_url*, when given, is the healed network-provenance URL to persist alongside
    the rotated tokens (key order in auth.json is preserved from the original login shape).
    """
    from arkos_cli.auth import _coerce_ttl_seconds
    now = datetime.now(timezone.utc)
    access_ttl = _coerce_ttl_seconds(refreshed.get("expires_in"))
    state["access_token"] = refreshed["access_token"]
    state["refresh_token"] = refreshed.get("refresh_token") or refresh_token
    state["token_type"] = refreshed.get("token_type") or state.get("token_type") or "Bearer"
    state["scope"] = refreshed.get("scope") or state.get("scope")
    if inference_base_url is not None:
        state["inference_base_url"] = inference_base_url
    state["obtained_at"] = now.isoformat()
    state["expires_in"] = access_ttl
    state["expires_at"] = _iso_after(now, access_ttl)


def _healed_portal_inference_url(refreshed: Dict[str, Any]) -> str:
    """Validated network-provenance inference URL from a refresh payload, healed to the default.

    A Portal URL rejected by the allowlist resets to the production default instead of leaving a
    previously-persisted bad host (e.g. a stale staging URL) in place — otherwise a poisoned
    auth.json re-validates to None on every refresh and silently re-uses the dead endpoint.
    """
    url = _validate_portal_inference_url_from_network(refreshed.get("inference_base_url"))
    return url or DEFAULT_PORTAL_INFERENCE_URL


def _portal_http_client(timeout_seconds: float, verify: Any) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(timeout_seconds), headers={"Accept": "application/json"},
        verify=verify)


def _model_priority(mid: str) -> tuple:
    """Sort key: opus > pro > haiku/flash > sonnet (sonnet is cheap/fast; best model first)."""
    low = mid.lower()
    rank = (0 if "opus" in low else 1 if "pro" in low and "sonnet" not in low
            else 3 if "sonnet" in low else 2)
    return (rank, mid)


def fetch_portal_models(
    *, inference_base_url: str, api_key: str, timeout_seconds: float = 15.0,
    verify: bool | str = True) -> List[str]:
    """Fetch available model IDs from the Portal inference API."""
    from arkos_cli.auth import _nonempty_str
    with _portal_http_client(timeout_seconds, verify) as client:
        response = client.get(
            f"{inference_base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}"})
    if response.status_code != 200:
        description = f"/models request failed with status {response.status_code}"
        try:
            err = response.json()
            description = str(err.get("error_description") or err.get("error") or description)
        except Exception as e:
            logger.debug("Could not parse error response JSON: %s", e)
        raise _portal_err(description, "models_fetch_failed")
    data = response.json().get("data")
    if not isinstance(data, list):
        return []
    model_ids: List[str] = []
    for item in data:
        model_id = item.get("id") if isinstance(item, dict) else None
        if _nonempty_str(model_id) and "arkos" not in model_id.lower():
            model_ids.append(model_id.strip())
    model_ids.sort(key=_model_priority)
    return list(dict.fromkeys(model_ids))


def _agent_key_is_usable(state: Dict[str, Any], min_ttl_seconds: int) -> bool:
    from arkos_cli.auth import _nonempty_str
    key = state.get("agent_key")
    return _nonempty_str(key) and _portal_invoke_jwt_is_usable(
        key, scope=state.get("scope"), expires_at=state.get("agent_key_expires_at"),
        min_ttl_seconds=max(0, int(min_ttl_seconds)))


def refresh_portal_oauth_pure(
    access_token: str, refresh_token: str, client_id: str, portal_base_url: str,
    inference_base_url: str, *, token_type: str = "Bearer", scope: str = DEFAULT_PORTAL_SCOPE,
    obtained_at: Optional[str] = None, expires_at: Optional[str] = None,
    agent_key: Optional[str] = None, agent_key_expires_at: Optional[str] = None,
    timeout_seconds: float = 15.0, insecure: Optional[bool] = None, ca_bundle: Optional[str] = None,
    force_refresh: bool = False,
    on_state_update: Optional[Callable[[Dict[str, Any], str], None]] = None) -> Dict[str, Any]:
    """Refresh Portal OAuth state without mutating auth.json directly.

    ``on_state_update`` fires after a successful access-token refresh so callers owning persistent
    state can save the rotated refresh token before later validation can fail.
    """
    return refresh_portal_oauth_from_state(
        {
            "access_token": access_token, "refresh_token": refresh_token, "client_id": client_id,
            "portal_base_url": portal_base_url, "inference_base_url": inference_base_url,
            "token_type": token_type, "scope": scope, "obtained_at": obtained_at,
            "expires_at": expires_at, "agent_key": agent_key,
            "agent_key_expires_at": agent_key_expires_at,
            "tls": {"insecure": insecure, "ca_bundle": ca_bundle}},
        timeout_seconds=timeout_seconds, force_refresh=force_refresh,
        on_state_update=on_state_update)


def refresh_portal_oauth_from_state(
    src: Dict[str, Any], *, timeout_seconds: float = 15.0, force_refresh: bool = False,
    on_state_update: Optional[Callable[[Dict[str, Any], str], None]] = None) -> Dict[str, Any]:
    """Refresh Portal OAuth from a state dict (defaults filled in) without mutating auth.json."""
    from arkos_cli.auth import (
        _assert_portal_inference_jwt_usable, _refresh_access_token, _resolve_verify,
        _select_portal_invoke_jwt)
    tls = src.get("tls") or {}
    insecure, ca_bundle = tls.get("insecure"), tls.get("ca_bundle")
    state: Dict[str, Any] = {
        "access_token": src.get("access_token", ""), "refresh_token": src.get("refresh_token", ""),
        "client_id": src.get("client_id") or DEFAULT_PORTAL_CLIENT_ID,
        "portal_base_url": (src.get("portal_base_url") or DEFAULT_PORTAL_URL).rstrip("/"),
        "inference_base_url": (
            src.get("inference_base_url") or DEFAULT_PORTAL_INFERENCE_URL).rstrip("/"),
        "token_type": src.get("token_type") or "Bearer",
        "scope": src.get("scope") or DEFAULT_PORTAL_SCOPE,
        "obtained_at": src.get("obtained_at"), "expires_at": src.get("expires_at"),
        "agent_key": src.get("agent_key"), "agent_key_expires_at": src.get("agent_key_expires_at"),
        "tls": {"insecure": bool(insecure), "ca_bundle": ca_bundle}}
    verify = _resolve_verify(insecure=insecure, ca_bundle=ca_bundle, auth_state=state)
    with _portal_http_client(timeout_seconds or 15.0, verify) as client:
        current_invoke_jwt_status = _state_invoke_jwt_status(state, state.get("access_token"))
        if force_refresh or current_invoke_jwt_status is not None:
            refresh_token_value = state.get("refresh_token")
            if not isinstance(refresh_token_value, str) or not refresh_token_value:
                if current_invoke_jwt_status is not None:
                    raise _unusable_invoke_jwt_error(
                        current_invoke_jwt_status, no_refresh_token=True)
                raise _portal_err("No refresh token is available for Arkos Portal.", relogin=True)
            refreshed = _refresh_access_token(
                client=client, portal_base_url=state["portal_base_url"],
                client_id=state["client_id"], refresh_token=refresh_token_value)
            _apply_portal_refreshed_tokens(
                state, refreshed, refresh_token_value,
                inference_base_url=_healed_portal_inference_url(refreshed))
            if on_state_update is not None:
                on_state_update(dict(state), "post_refresh_access_token")
        _assert_portal_inference_jwt_usable(state)
        _select_portal_invoke_jwt(state)
    return state


def persist_portal_credentials(creds: Dict[str, Any], *, label: Optional[str] = None):
    """Persist Portal OAuth credentials as the singleton provider state.

    Portal credentials are read from ``providers.portal`` (401 recovery, pool seeding) AND
    ``credential_pool.portal`` (runtime ``pool.select()``); a pool-only write broke expiry recovery.
    So: write the singleton, mirror to the shared store, then ``load_pool("portal")`` upserts the
    canonical ``device_code`` entry in place. ``label`` rides in the singleton so re-seeding keeps
    it.
    """
    from arkos_cli.auth import _save_active_provider_state, _write_shared_portal_state
    from agent.credential_pool import load_pool
    state = dict(creds)
    if label and str(label).strip():
        state["label"] = str(label).strip()
    _save_active_provider_state("portal", state)
    _write_shared_portal_state(state)
    pool = load_pool("portal")
    return next((e for e in pool.entries() if e.source == PORTAL_DEVICE_CODE_SOURCE), None)


def _sync_portal_pool_from_auth_store() -> None:
    """Best-effort pool reseed after providers.portal changes; never fail login."""
    try:
        from agent.credential_pool import load_pool
        load_pool("portal")
    except Exception as exc:
        logger.debug("Failed to sync Portal credential pool from auth store: %s", exc)


def _portal_effective_routing(state: Dict[str, Any]) -> tuple[str, str, str, str]:
    """``(portal_url, stored_inference_url, effective_inference_url, client_id)`` from *state*.

    The stored inference URL is re-validated network-provenance (persisted); the effective one
    layers the runtime-only ``PORTAL_INFERENCE_BASE_URL`` override on top and is never persisted.
    """
    from arkos_cli.auth import _PORTAL_ALLOWED_HOSTS, _optional_base_url
    portal_url = (
        _optional_base_url(state.get("portal_base_url")) or os.getenv("ARKOS_PORTAL_BASE_URL")
        or os.getenv("PORTAL_BASE_URL") or DEFAULT_PORTAL_URL).rstrip("/")
    env_portal_override = _portal_env_override()
    if env_portal_override:
        portal_url = env_portal_override.rstrip("/")
    else:
        parsed_portal_url = urlparse(portal_url)
        portal_host, scheme = parsed_portal_url.hostname, parsed_portal_url.scheme
        trusted_scheme = scheme == "https" or (
            scheme == "http" and portal_host in {"localhost", "127.0.0.1"})
        if not portal_host or portal_host not in _PORTAL_ALLOWED_HOSTS or not trusted_scheme:
            logger.warning(
                "auth: ignoring invalid portal_base_url %r "
                "(host %r or scheme not allowed), using default",
                portal_url, portal_host)
            portal_url = DEFAULT_PORTAL_URL
    stored_inference_url = (
        _validate_portal_inference_url_from_network(
            _optional_base_url(state.get("inference_base_url")))
        or DEFAULT_PORTAL_INFERENCE_URL)
    return (
        portal_url, stored_inference_url, _portal_inference_env_override() or stored_inference_url,
        str(state.get("client_id") or DEFAULT_PORTAL_CLIENT_ID))


class _PortalRuntimeResolve:
    """Working set for one ``resolve_portal_runtime_credentials`` call.

    Holds the token pair + routing tuple that shared-store merges / refreshes replace mid-flight.
    ``persist`` skips writes where only derived TTL countdowns changed (keeps the mtime-keyed
    auth-status cache warm) and mirrors every real write to the shared store (best-effort).
    """

    def __init__(
        self, auth_store: Dict[str, Any], state: Dict[str, Any], state_source_path: Optional[Path],
        *, force_refresh: bool, stale_access_token: Optional[str], timeout_seconds: float) -> None:
        self.auth_store, self.state, self._source_path = auth_store, state, state_source_path
        self.force_refresh, self.stale_access_token = force_refresh, stale_access_token
        self.timeout_seconds = timeout_seconds
        self.sequence_id = uuid.uuid4().hex[:12]
        self._persisted_state = dict(state)
        self.persisted_any = False
        self.access_token = state.get("access_token")
        self.refresh_token = state.get("refresh_token")
        self._reload_routing()

    def _reload_routing(self) -> None:
        (self.portal_base_url, self.stored_inference_base_url, self.inference_base_url,
         self.client_id) = _portal_effective_routing(self.state)

    def persist(self, reason: str) -> None:
        from arkos_cli.auth import _save_provider_state_to_source, _write_shared_portal_state
        state = self.state
        persisted = _portal_effective_provider_state(self._persisted_state)
        if _portal_effective_provider_state(state) == persisted:
            _oauth_trace("portal_state_persist_skipped", sequence_id=self.sequence_id, reason=reason)
            return
        try:
            _save_provider_state_to_source(self.auth_store, "portal", state, self._source_path)
        except Exception as exc:
            _oauth_trace(
                "portal_state_persist_failed", sequence_id=self.sequence_id, reason=reason,
                error_type=type(exc).__name__)
            raise
        _oauth_trace(
            "portal_state_persisted", sequence_id=self.sequence_id, reason=reason,
            refresh_token_fp=_token_fingerprint(state.get("refresh_token")),
            access_token_fp=_token_fingerprint(state.get("access_token")))
        self._persisted_state = dict(state)
        self.persisted_any = True
        _write_shared_portal_state(state)

    def shared_lock(self):
        return _portal_shared_store_lock(timeout_seconds=_shared_lock_timeout(self.timeout_seconds))

    def has_access_token(self) -> bool:
        return isinstance(self.access_token, str) and bool(self.access_token)

    def invoke_jwt_status(self) -> Optional[str]:
        return _state_invoke_jwt_status(self.state, self.access_token)

    def merge_shared(self) -> bool:
        """Adopt fresher shared-store tokens (caller holds the shared lock). True when merged."""
        if not _merge_shared_portal_oauth_state(self.state):
            return False
        self.access_token = self.state.get("access_token")
        self.refresh_token = self.state.get("refresh_token")
        self._reload_routing()
        return True

    def skip_refresh_if_peer_rotated(self) -> None:
        """Skip the refresh when a peer already rotated the grant.

        Under the store lock: if the bearer that failed upstream is no longer the one on disk and
        the on-disk one is usable, adopt it — never re-POST the shared grant.
        """
        token = self.access_token
        if (self.force_refresh and self.stale_access_token and isinstance(token, str) and token
                and token != self.stale_access_token and self.invoke_jwt_status() is None):
            _oauth_trace(
                "refresh_skipped_peer_rotated", sequence_id=self.sequence_id,
                access_token_fp=_token_fingerprint(token))
            self.force_refresh = False

    def refresh(self, client: httpx.Client, invoke_jwt_status: Optional[str]) -> None:
        """Redeem the refresh token, apply + persist the rotated pair (caller holds both locks)."""
        if not isinstance(self.refresh_token, str) or not self.refresh_token:
            raise _unusable_invoke_jwt_error(
                invoke_jwt_status or "force_refresh", no_refresh_token=True)
        refresh_reason = (
            "force_refresh" if self.force_refresh else (invoke_jwt_status or "access_unusable"))
        _oauth_trace(
            "refresh_start", sequence_id=self.sequence_id, reason=refresh_reason,
            refresh_token_fp=_token_fingerprint(self.refresh_token))
        refreshed = _refresh_portal_or_quarantine(
            client=client, auth_store=self.auth_store, state=self.state,
            portal_base_url=self.portal_base_url, client_id=self.client_id,
            refresh_token=self.refresh_token, reason="runtime_access_refresh_failure",
            persist=lambda: self.persist("terminal_runtime_access_refresh_failure"))
        previous_refresh_token = self.refresh_token
        self.stored_inference_base_url = _healed_portal_inference_url(refreshed)
        self.inference_base_url = _portal_inference_env_override() or self.stored_inference_base_url
        _apply_portal_refreshed_tokens(
            self.state, refreshed, self.refresh_token,
            inference_base_url=self.stored_inference_base_url)
        self.access_token = self.state["access_token"]
        self.refresh_token = self.state["refresh_token"]
        _oauth_trace(
            "refresh_success", sequence_id=self.sequence_id, reason=refresh_reason,
            previous_refresh_token_fp=_token_fingerprint(previous_refresh_token),
            new_refresh_token_fp=_token_fingerprint(self.refresh_token))
        self.persist("post_refresh_access_token")

    def ensure_usable_access_token(self, client: httpx.Client) -> None:
        """Merge from the shared store / refresh until the access token is a usable invoke JWT."""
        if not self.has_access_token():
            with self.shared_lock():
                if self.merge_shared():
                    self.persist("runtime_shared_merge_missing_access_token")
        if not self.has_access_token():
            raise _portal_err("No access token found for Arkos Portal login.", relogin=True)
        invoke_jwt_status = self.invoke_jwt_status()
        self.skip_refresh_if_peer_rotated()
        if not (self.force_refresh or invoke_jwt_status is not None):
            return
        with self.shared_lock():
            if self.merge_shared():
                invoke_jwt_status = self.invoke_jwt_status()
                self.persist("post_shared_merge_access_unusable")
                self.skip_refresh_if_peer_rotated()
            if self.force_refresh or invoke_jwt_status is not None:
                self.refresh(client, invoke_jwt_status)


def resolve_portal_runtime_credentials(
    *, timeout_seconds: float = 15.0, insecure: Optional[bool] = None,
    ca_bundle: Optional[str] = None, force_refresh: bool = False,
    stale_access_token: Optional[str] = None) -> Dict[str, Any]:
    """Resolve Portal inference credentials for runtime use (refreshing under the auth-store lock).

    ``stale_access_token`` is the bearer that just failed upstream (401): with ``force_refresh``,
    the refresh POST is skipped if the store (re-read under the lock) already holds a *different*
    usable token — a peer won the rotation; adopt it rather than invalidate a sibling's token.
    """
    from arkos_cli.auth import (
        _assert_portal_inference_jwt_usable, _auth_file_path, _provider_state_transaction,
        _resolve_verify, _select_portal_invoke_jwt, _sync_portal_pool_from_auth_store,
        _tls_state_from_verify)
    with _provider_state_transaction("portal") as (auth_store, state, state_source_path):
        if not state:
            raise _portal_err("Arkos is not logged into Arkos Portal.", relogin=True)
        run = _PortalRuntimeResolve(
            auth_store, state, state_source_path, force_refresh=force_refresh,
            stale_access_token=stale_access_token, timeout_seconds=timeout_seconds)
        verify = _resolve_verify(insecure=insecure, ca_bundle=ca_bundle, auth_state=state)
        _oauth_trace(
            "portal_runtime_credentials_start", sequence_id=run.sequence_id,
            refresh_token_fp=_token_fingerprint(state.get("refresh_token")))
        with _portal_http_client(timeout_seconds or 15.0, verify) as client:
            run.ensure_usable_access_token(client)
            _assert_portal_inference_jwt_usable(state, access_token=run.access_token)
            _select_portal_invoke_jwt(
                state, access_token=run.access_token, sequence_id=run.sequence_id)
            state.update(
                portal_base_url=run.portal_base_url, client_id=run.client_id,
                inference_base_url=run.stored_inference_base_url,
                tls=_tls_state_from_verify(verify))
        run.persist("resolve_portal_runtime_credentials_final")
    if run.persisted_any:
        _sync_portal_pool_from_auth_store()
    api_key = state.get("agent_key")
    if not isinstance(api_key, str) or not api_key:
        raise _portal_err("Failed to resolve a Portal inference API key", "server_error")
    expires_at = state.get("agent_key_expires_at")
    return {
        "provider": "portal", "base_url": run.inference_base_url, "api_key": api_key,
        "key_id": state.get("agent_key_id"), "expires_at": expires_at,
        "expires_in": _remaining_ttl(expires_at, state.get("agent_key_expires_in")),
        "source": PORTAL_AUTH_PATH_INVOKE_JWT,
        "auth_path": PORTAL_AUTH_PATH_INVOKE_JWT,
        "state_path": str(state_source_path or _auth_file_path())}


def _empty_portal_auth_status() -> Dict[str, Any]:
    return {
        "logged_in": False, "portal_base_url": None, "inference_base_url": None,
        "access_expires_at": None, "agent_key_expires_at": None, "has_refresh_token": False,
        "inference_credential_present": False, "credential_source": None}


def _snapshot_portal_pool_status() -> Dict[str, Any]:
    """Best-effort status from the credential pool.

    Fallback only: the auth-store provider state is the runtime source of truth because it is what
    ``resolve_portal_runtime_credentials()`` refreshes.
    """
    from arkos_cli.auth import _parse_iso_timestamp
    try:
        from agent.credential_pool import load_pool
        pool = load_pool("portal")
        entries = list(pool.entries()) if pool and pool.has_credentials() else []
        if not entries:
            return _empty_portal_auth_status()
        entry = max(entries, key=lambda e: (
            _parse_iso_timestamp(getattr(e, "agent_key_expires_at", None)) or 0.0,
            _parse_iso_timestamp(getattr(e, "expires_at", None)) or 0.0,
            -int(getattr(e, "priority", 0) or 0)))
        attr = lambda name, default=None: getattr(entry, name, default)  # noqa: E731
        if not attr("runtime_api_key"):
            return _empty_portal_auth_status()
        access_token, refresh_token = attr("access_token"), attr("refresh_token")
        auth_type = str(attr("auth_type", "") or "").strip().lower()
        is_portal_oauth = bool(access_token) and (
            auth_type.startswith("oauth") or bool(refresh_token))
        label = attr("label", "unknown")
        return {
            "logged_in": is_portal_oauth,
            "portal_base_url": (
                (attr("portal_base_url") or DEFAULT_PORTAL_URL) if is_portal_oauth else None),
            "inference_base_url": (
                attr("inference_base_url") or attr("runtime_base_url") or attr("base_url")),
            "access_token": access_token if is_portal_oauth else None,
            "access_expires_at": attr("expires_at"),
            "agent_key_expires_at": attr("agent_key_expires_at"),
            "has_refresh_token": bool(refresh_token), "inference_credential_present": True,
            "credential_source": f"pool:{label}", "source": f"pool:{label}"}
    except Exception:
        return _empty_portal_auth_status()


def _portal_status_from_state(
    state: Dict[str, Any], *, logged_in: bool, source: str) -> Dict[str, Any]:
    """Auth-store-backed Portal status snapshot (shared by the live and refresh-free variants)."""
    access_token = state.get("access_token")
    return {
        "logged_in": logged_in, "portal_base_url": state.get("portal_base_url"),
        "inference_base_url": state.get("inference_base_url"),
        "access_expires_at": state.get("expires_at"),
        "agent_key_expires_at": state.get("agent_key_expires_at"),
        "has_refresh_token": bool(state.get("refresh_token")), "access_token": access_token,
        "inference_credential_present": bool(access_token or state.get("agent_key")),
        "credential_source": "auth_store", "source": source}


def _compute_portal_auth_status() -> Dict[str, Any]:
    """Uncached implementation of get_portal_auth_status(). See that function."""
    from arkos_cli.auth import get_provider_auth_state, resolve_portal_runtime_credentials
    state = get_provider_auth_state("portal")
    if not state:
        return _snapshot_portal_pool_status()
    base_status = _portal_status_from_state(
        state, logged_in=bool(state.get("access_token")), source="auth_store")
    try:
        creds = resolve_portal_runtime_credentials()
        refreshed_state = get_provider_auth_state("portal") or state
        base_status.update({
            "logged_in": True,
            "portal_base_url": (
                refreshed_state.get("portal_base_url") or base_status.get("portal_base_url")),
            "inference_base_url": (
                creds.get("base_url") or refreshed_state.get("inference_base_url")
                or base_status.get("inference_base_url")),
            "access_expires_at": (
                refreshed_state.get("expires_at") or base_status.get("access_expires_at")),
            "agent_key_expires_at": (
                creds.get("expires_at") or refreshed_state.get("agent_key_expires_at")
                or base_status.get("agent_key_expires_at")),
            "has_refresh_token": bool(refreshed_state.get("refresh_token")),
            "inference_credential_present": True, "credential_source": "auth_store",
            "source": f"runtime:{creds.get('source', 'portal')}", "key_id": creds.get("key_id")})
    except AuthError as exc:
        base_status.update({
            "logged_in": False, "error": str(exc),
            "relogin_required": bool(getattr(exc, "relogin_required", False)),
            "error_code": getattr(exc, "code", None)})
    return base_status


def _terminal_quarantine_marker(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The persisted ``last_auth_error`` when it is a terminal quarantine with no credential left.

    Only terminal while there is no usable credential: if a later login repopulated tokens the stale
    marker must not keep reporting terminal.
    """
    last_err = state.get("last_auth_error")
    if (isinstance(last_err, dict) and last_err.get("relogin_required")
            and not (state.get("access_token") or state.get("refresh_token"))):
        return last_err
    return None


def get_portal_auth_status_local() -> Dict[str, Any]:
    """Refresh-free Portal auth snapshot for read-only display surfaces.

    NEVER calls ``resolve_portal_runtime_credentials()`` (no refresh POST / single-use token spent);
    ``logged_in`` = usable invoke JWT, or a refresh token not terminally quarantined — not proof
    the server still accepts it.
    """
    from arkos_cli.auth import get_provider_auth_state
    try:
        state = get_provider_auth_state("portal")
    except Exception:
        state = None
    if not state:
        return _snapshot_portal_pool_status()
    jwt_reason = _state_invoke_jwt_status(state, state.get("access_token"))
    last_err = _terminal_quarantine_marker(state)
    logged_in = (jwt_reason is None) or (bool(state.get("refresh_token")) and last_err is None)
    status = _portal_status_from_state(state, logged_in=logged_in, source="auth_store_local")
    if last_err is not None:
        status.update(
            relogin_required=True, error_code=last_err.get("code"),
            error=last_err.get("message") or "re-login required")
    return status


PORTAL_SESSION_VALID = "valid"
PORTAL_SESSION_TERMINAL = "terminal"
PORTAL_SESSION_UNKNOWN = "unknown"


def get_portal_session_validity() -> str:
    """Classify the Portal bootstrap session for the dashboard /api/status probe.

    Local auth-store state only; polled frequently, so it never resolves or refreshes. ANTI-FLAP:
    only a *terminal* failure maps to "terminal" — a rotation blip, network error, or expiring
    token must NOT (that would trigger a spurious Portal re-mint on a healthy box).
    """
    from arkos_cli.auth import get_provider_auth_state
    try:
        state = get_provider_auth_state("portal")
    except Exception:
        state = None
    if not state:
        return PORTAL_SESSION_UNKNOWN
    if _terminal_quarantine_marker(state) is not None:
        return PORTAL_SESSION_TERMINAL
    if _state_invoke_jwt_status(state, state.get("access_token")) is None:
        return PORTAL_SESSION_VALID
    return PORTAL_SESSION_UNKNOWN


def _pool_first_oauth_status(
    provider_id: str, *, is_expiring: Callable[[str, int], bool], auth_mode: str,
    resolve: Callable[[], Dict[str, Any]],
    on_pool_miss: Optional[Callable[[], Optional[Dict[str, Any]]]] = None) -> Dict[str, Any]:
    """Status snapshot for a store-backed OAuth provider (Codex, xAI).

    Pool first (where `arkos auth` / `arkos model` store device_code tokens), then
    *on_pool_miss* for a pool-derived degraded status, then the legacy state via *resolve*.
    """
    from arkos_cli.auth import _auth_file_path
    try:
        from agent.credential_pool import load_pool
        pool = load_pool(provider_id)
        if pool and pool.has_credentials():
            entry = pool.select()
            if entry is not None:
                api_key = (
                    getattr(entry, "runtime_api_key", None) or getattr(entry, "access_token", ""))
                if api_key and not is_expiring(api_key, 0):
                    return {
                        "logged_in": True, "auth_store": str(_auth_file_path()),
                        "last_refresh": getattr(entry, "last_refresh", None),
                        "auth_mode": auth_mode,
                        "source": f"pool:{getattr(entry, 'label', 'unknown')}", "api_key": api_key}
            if on_pool_miss is not None and (degraded := on_pool_miss()):
                return degraded
    except Exception:
        pass
    try:
        creds = resolve()
        return {
            "logged_in": True, "auth_store": str(_auth_file_path()),
            "last_refresh": creds.get("last_refresh"),
            "auth_mode": creds.get("auth_mode"), "source": creds.get("source"),
            "api_key": creds.get("api_key")}
    except AuthError as exc:
        return {"logged_in": False, "auth_store": str(_auth_file_path()), "error": str(exc)}


def _portal_device_code_login(
    *, portal_base_url: Optional[str] = None, inference_base_url: Optional[str] = None,
    client_id: Optional[str] = None, scope: Optional[str] = None, open_browser: bool = True,
    timeout_seconds: float = 15.0, insecure: bool = False, ca_bundle: Optional[str] = None,
    on_verification: Optional[Callable[[str, str], None]] = None) -> Dict[str, Any]:
    """Run the Portal device-code flow and return full OAuth state without persisting."""
    from arkos_cli.auth import (
        PROVIDER_REGISTRY, _coerce_ttl_seconds, _is_remote_session, _optional_base_url,
        _poll_for_token, _print_device_code_instructions, _request_device_code,
        _tls_state_from_verify, format_auth_error, refresh_portal_oauth_from_state)
    pconfig = PROVIDER_REGISTRY["portal"]
    portal_base_url = (
        portal_base_url or os.getenv("ARKOS_PORTAL_BASE_URL") or os.getenv("PORTAL_BASE_URL")
        or pconfig.portal_base_url).rstrip("/")
    requested_inference_url = (
        inference_base_url or os.getenv("PORTAL_INFERENCE_BASE_URL")
        or pconfig.inference_base_url).rstrip("/")
    client_id = client_id or pconfig.client_id
    scope = scope or pconfig.scope
    verify: bool | str = False if insecure else (ca_bundle if ca_bundle else True)
    if not portal_base_url:
        raise AuthError("Arkos Portal login is disabled. Please configure a direct provider API key (e.g. arkos auth add <provider>).")
    print(f"Starting Arkos login via {pconfig.name}...")
    if insecure:
        print("TLS verification: disabled (--insecure)")
    elif ca_bundle:
        print(f"TLS verification: custom CA bundle ({ca_bundle})")
    with _portal_http_client(timeout_seconds, verify) as client:
        device_data = _request_device_code(
            client=client, portal_base_url=portal_base_url, client_id=client_id, scope=scope)
        verification_url = str(device_data["verification_uri_complete"])
        user_code = str(device_data["user_code"])
        expires_in = int(device_data["expires_in"])
        interval = int(device_data["interval"])
        _print_device_code_instructions(
            verification_url, user_code, open_browser=open_browser, failure_dash="—")
        if on_verification is not None:
            with suppress(Exception):
                on_verification(verification_url, user_code)
        effective_interval = max(1, min(interval, DEVICE_AUTH_POLL_INTERVAL_CAP_SECONDS))
        print(f"Waiting for approval (polling every {effective_interval}s)...")
        token_data = _poll_for_token(
            client=client, portal_base_url=portal_base_url, client_id=client_id,
            device_code=str(device_data["device_code"]), expires_in=expires_in,
            poll_interval=interval)
    now = datetime.now(timezone.utc)
    token_expires_in = _coerce_ttl_seconds(token_data.get("expires_in", 0))
    resolved_inference_url = (
        _optional_base_url(token_data.get("inference_base_url")) or requested_inference_url)
    if resolved_inference_url != requested_inference_url:
        print(f"Using portal-provided inference URL: {resolved_inference_url}")
    auth_state = {
        "portal_base_url": portal_base_url, "inference_base_url": resolved_inference_url,
        "client_id": client_id, "scope": token_data.get("scope") or scope,
        "token_type": token_data.get("token_type", "Bearer"),
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token"),
        "obtained_at": now.isoformat(), "expires_at": _iso_after(now, token_expires_in),
        "expires_in": token_expires_in, "tls": _tls_state_from_verify(verify),
        **_PORTAL_EMPTY_AGENT_KEY_FIELDS}
    try:
        return refresh_portal_oauth_from_state(
            auth_state, timeout_seconds=timeout_seconds, force_refresh=False)
    except AuthError as exc:
        if exc.code == "subscription_required":
            portal_url = auth_state.get("portal_base_url", DEFAULT_PORTAL_URL).rstrip("/")
            print()
            print(format_auth_error(exc))
            print(f"  Subscribe here: {portal_url}/billing")
            print()
            print("After subscribing, run `arkos model` again to finish setup.")
            raise SystemExit(1)
        raise


def _mirror_portal_state_best_effort(auth_state: Dict[str, Any]) -> None:
    """Mirror to the shared store + reseed the pool, swallowing all errors (same as _login_portal)."""
    from arkos_cli.auth import _sync_portal_pool_from_auth_store, _write_shared_portal_state
    with suppress(Exception):
        _write_shared_portal_state(auth_state)
    with suppress(Exception):
        _sync_portal_pool_from_auth_store()


def step_up_portal_billing_scope(
    *, open_browser: bool = True, timeout_seconds: float = 15.0,
    on_verification: Optional[Callable[[str, str], None]] = None) -> bool:
    """Re-run the device flow requesting ``billing:manage`` (step-up on 403 insufficient_scope).

    The user must be ADMIN/OWNER and select "Allow Remote Spending" in the portal, else the
    server silently downscopes and this returns False. Persists like ``_login_portal`` minus the
    model picker.
    """
    from arkos_cli.auth import (
        PROVIDER_REGISTRY, _portal_device_code_login, _save_active_provider_state,
        get_provider_auth_state)
    prior = get_provider_auth_state("portal") or {}
    pconfig = PROVIDER_REGISTRY["portal"]
    _raw_scope = prior.get("scope")
    prior_scope = _raw_scope.split() if isinstance(_raw_scope, str) else []
    requested = list(dict.fromkeys([
        *(prior_scope or [PORTAL_INFERENCE_INVOKE_SCOPE, "tool:invoke"]), PORTAL_BILLING_MANAGE_SCOPE]))
    auth_state = _portal_device_code_login(
        portal_base_url=prior.get("portal_base_url") or None,
        inference_base_url=prior.get("inference_base_url") or None,
        client_id=prior.get("client_id") or pconfig.client_id, scope=" ".join(requested),
        open_browser=open_browser, timeout_seconds=timeout_seconds, on_verification=on_verification)
    _save_active_provider_state("portal", auth_state)
    _mirror_portal_state_best_effort(auth_state)
    granted = auth_state.get("scope")
    return isinstance(granted, str) and PORTAL_BILLING_MANAGE_SCOPE in granted.split()


def _pick_portal_model_after_login(
    auth_state: Dict[str, Any], inference_base_url: str) -> Optional[str]:
    """Fetch the curated Portal model list (tier/policy-filtered) and run the interactive picker.

    Returns the selected model id, or None when the user skipped / nothing was selectable.
    Raises on any fetch failure so the caller can print the "Login succeeded, but..." notice.
    """
    from arkos_cli.auth import _prompt_model_selection
    runtime_key = auth_state.get("agent_key") or auth_state.get("access_token")
    if not isinstance(runtime_key, str) or not runtime_key:
        raise _portal_err("No runtime API key available to fetch models", "invalid_token")
    from arkos_cli.models import (
        get_curated_portal_model_ids,
        check_portal_free_tier,
        partition_portal_models_by_tier,
        union_with_portal_free_recommendations,
        union_with_portal_paid_recommendations,
    )
    from arkos_cli.models_pricing import (
        get_pricing_for_provider,
        portal_policy_allowed_ids,
        restrict_to_portal_policy,
    )
    model_ids = get_curated_portal_model_ids()
    _portal = auth_state.get("portal_base_url", "")
    print()
    unavailable_models: list = []
    unavailable_message = ""
    _policy_narrowed = False
    if model_ids:
        pricing = get_pricing_for_provider("portal")
        free_tier = check_portal_free_tier(force_fresh=True)
        _policy_allowed = portal_policy_allowed_ids()
        if free_tier:
            with suppress(Exception):
                unavailable_message = _portal_entitlement_message("paid Portal models")
        union = (
            union_with_portal_free_recommendations if free_tier
            else union_with_portal_paid_recommendations)
        model_ids, pricing = union(model_ids, pricing, _portal)
        _before_policy = model_ids
        model_ids = restrict_to_portal_policy(model_ids, _policy_allowed, rescue_empty=True)
        _policy_narrowed = model_ids != _before_policy
        if free_tier:
            model_ids, unavailable_models = partition_portal_models_by_tier(
                model_ids, pricing, free_tier=True)
    if model_ids:
        from arkos_cli.portal_account import portal_policy_notice
        _policy_notice = portal_policy_notice(removed=_policy_narrowed)
        if _policy_notice:
            print(_policy_notice)
        print(
            f"Showing {len(model_ids)} curated models — "
            "use \"Enter custom model name\" for others.")
        return _prompt_model_selection(
            model_ids, pricing=pricing, unavailable_models=unavailable_models, portal_url=_portal,
            unavailable_message=unavailable_message, confirm_provider="portal",
            confirm_base_url=inference_base_url, confirm_api_key=runtime_key)
    if unavailable_models:
        _url = (_portal or DEFAULT_PORTAL_URL).rstrip("/")
        print("No free models currently available.")
        print(unavailable_message or f"Upgrade at {_url} to access paid models.")
    else:
        print("No curated models available for Arkos Portal.")
    return None


def _offer_shared_portal_import(timeout_seconds: float) -> Optional[Dict[str, Any]]:
    """Codex-style auto-import: offer to rehydrate a Portal credential from another profile.

    Checks the shared store before launching a fresh device-code flow. Returns the refreshed
    auth state when the user accepted and the import succeeded, else None.
    """
    from arkos_cli.auth import _prompt_yes_no, _read_shared_portal_state
    shared = _read_shared_portal_state()
    if not shared:
        return None
    try:
        shared_path = _portal_shared_store_path()
    except RuntimeError:
        shared_path = None
    print()
    print(f"Found existing Portal OAuth credentials at {shared_path}" if shared_path
          else "Found existing shared Portal OAuth credentials")
    if not _prompt_yes_no("Import these credentials? [Y/n]: ", default="y"):
        return None
    print("Rehydrating Portal session from shared credentials...")
    auth_state = _try_import_shared_portal_state(timeout_seconds=timeout_seconds)
    if auth_state is None:
        print("Could not refresh shared credentials — falling back to device-code login.")
    return auth_state


def _restore_active_provider(prior_active_provider: Any) -> None:
    """Undo the ``active_provider="portal"`` that ``_save_provider_state`` wrote during login."""
    from arkos_cli.auth import _auth_store_lock, _load_auth_store, _save_auth_store
    with _auth_store_lock():
        auth_store = _load_auth_store()
        if prior_active_provider:
            auth_store["active_provider"] = prior_active_provider
        else:
            auth_store.pop("active_provider", None)
        _save_auth_store(auth_store)


def _login_portal(args, pconfig: ProviderConfig) -> None:
    """Arkos Portal device authorization flow."""
    from arkos_cli.auth import (
        _auth_store_lock, _load_auth_store, _portal_device_code_login, _save_active_provider_state,
        _save_model_choice, _sync_portal_pool_from_auth_store, _update_config_for_provider,
        _write_shared_portal_state, format_auth_error)
    timeout_seconds = getattr(args, "timeout", None) or 15.0
    ca_bundle = (
        getattr(args, "ca_bundle", None) or os.getenv("ARKOS_CA_BUNDLE")
        or os.getenv("SSL_CERT_FILE"))
    try:
        auth_state = _offer_shared_portal_import(timeout_seconds)
        if auth_state is None:
            auth_state = _portal_device_code_login(
                portal_base_url=getattr(args, "portal_url", None),
                inference_base_url=getattr(args, "inference_url", None),
                client_id=getattr(args, "client_id", None) or pconfig.client_id,
                scope=getattr(args, "scope", None),
                open_browser=not getattr(args, "no_browser", False),
                timeout_seconds=timeout_seconds, insecure=bool(getattr(args, "insecure", False)),
                ca_bundle=ca_bundle)
        inference_base_url = auth_state["inference_base_url"]
        with _auth_store_lock():
            prior_active_provider = _load_auth_store().get("active_provider")
        saved_to = _save_active_provider_state("portal", auth_state)
        _write_shared_portal_state(auth_state)
        _sync_portal_pool_from_auth_store()
        print()
        print("Login successful!")
        print(f"  Auth state: {saved_to}")
        selected_model = None
        try:
            selected_model = _pick_portal_model_after_login(auth_state, inference_base_url)
        except Exception as exc:
            message = format_auth_error(exc) if isinstance(exc, AuthError) else str(exc)
            print()
            print(f"Login succeeded, but could not fetch available models. Reason: {message}")
        if not selected_model:
            _restore_active_provider(prior_active_provider)
            print()
            print("No provider change. Portal credentials saved for future use.")
            print("  Run `arkos model` again to switch to Arkos Portal.")
            return
        config_path = _update_config_for_provider(
            "portal", inference_base_url, default_model=selected_model)
        _save_model_choice(selected_model)
        print(f"Default model set to: {selected_model}")
        print(f"  Config updated: {config_path} (model.provider=portal)")
    except KeyboardInterrupt:
        print("\nLogin cancelled.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"Login failed: {exc}")
        raise SystemExit(1)
