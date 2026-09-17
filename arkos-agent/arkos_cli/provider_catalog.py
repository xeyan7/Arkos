"""Unified provider catalog — one source of truth for the provider universe.

The provider list shown by ``arkos model`` (CLI/TUI) and the desktop Settings → Providers tabs
(Accounts + API keys) **must be the same set**; providers added after those lists were written
silently went missing from the GUI. ``auth_type`` / ``api_key_env_vars`` / ``base_url_env_var``
come from :data:`arkos_cli.auth.PROVIDER_REGISTRY` (credential truth); ``display_name`` /
``description`` / ``signup_url`` from the provider's :class:`providers.base.ProviderProfile`, falling
back to the ``CANONICAL_PROVIDERS`` entry's ``label`` / ``tui_desc`` and the ``OPTIONAL_ENV_VARS``
signup URL (many profiles leave these blank, and lmstudio, openai-api, tencent-tokenhub, xai-oauth
have no profile at all — the fallbacks are load-bearing).
"""

from __future__ import annotations

from dataclasses import dataclass

_ACCOUNTS_AUTH_TYPES: frozenset[str] = frozenset(
    {"oauth_device_code", "oauth_external", "oauth_minimax", "external_process", "copilot"}
)


@dataclass(frozen=True)
class ProviderDescriptor:
    """One provider, as seen by every surface (CLI picker + both GUI tabs)."""

    slug: str
    label: str
    description: str
    auth_type: str
    tab: str
    api_key_env_vars: tuple[str, ...]
    base_url_env_var: str
    signup_url: str
    order: int
    keyless: bool = False


def tab_for_auth_type(auth_type: str) -> str:
    """Return the desktop tab ("keys"|"accounts") a provider's auth maps to."""
    return "accounts" if auth_type in _ACCOUNTS_AUTH_TYPES else "keys"


def _is_url_var(name: str) -> bool:
    return name.endswith("_BASE_URL") or name.endswith("_URL")


def _split_env_vars(env_vars: tuple[str, ...]) -> tuple[tuple[str, ...], str]:
    """Split a profile's ``env_vars`` into (api_key_vars, base_url_var)."""
    return tuple(v for v in env_vars if not _is_url_var(v)), next((v for v in env_vars if _is_url_var(v)), "")


def _safe_import(module: str, attr: str, default):
    """Import ``attr`` from ``module``; ``default`` on ANY failure — this module is on the import
    path of the web server and the CLI, and a provider-plugin import error must never blank the
    whole catalog."""
    try:
        return getattr(__import__(module, fromlist=[attr]), attr)
    except Exception:
        return default


def provider_catalog() -> list[ProviderDescriptor]:
    """One descriptor per provider in the ``arkos model`` universe (:data:`CANONICAL_PROVIDERS`,
    auto-extended by provider plugins). Auth/env from ``PROVIDER_REGISTRY``; display metadata from
    ``ProviderProfile`` with canonical/env fallbacks so profile-less providers still resolve."""
    from arkos_cli.models import CANONICAL_PROVIDERS
    PROVIDER_REGISTRY = _safe_import("arkos_cli.auth", "PROVIDER_REGISTRY", {})
    OPTIONAL_ENV_VARS = _safe_import("arkos_cli.config", "OPTIONAL_ENV_VARS", {})
    ARKOS_OVERLAYS = _safe_import("arkos_cli.providers", "ARKOS_OVERLAYS", {})
    try:
        from providers import list_providers
        profiles = {p.name: p for p in list_providers()}
    except Exception:
        profiles = {}
    out: list[ProviderDescriptor] = []
    for order, entry in enumerate(CANONICAL_PROVIDERS):
        slug = entry.slug
        cfg = PROVIDER_REGISTRY.get(slug)
        prof = profiles.get(slug)
        overlay = ARKOS_OVERLAYS.get(slug)
        auth_type = ((cfg.auth_type if cfg else "") or (prof.auth_type if prof else "")
                     or (overlay.auth_type if overlay else "") or "api_key")
        if cfg and cfg.api_key_env_vars:
            api_key_vars, base_url_var = tuple(cfg.api_key_env_vars), cfg.base_url_env_var or ""
        elif prof and prof.env_vars:
            api_key_vars, base_url_var = _split_env_vars(tuple(prof.env_vars))
        else:
            api_key_vars, base_url_var = (), ""
        label = (prof.display_name if prof else "") or entry.label or slug
        signup_url = (prof.signup_url if prof else "") or ""
        if not signup_url and api_key_vars:
            signup_url = (OPTIONAL_ENV_VARS.get(api_key_vars[0]) or {}).get("url") or ""
        out.append(
            ProviderDescriptor(
                slug=slug, label=label, description=(prof.description if prof else "") or entry.tui_desc or label,
                auth_type=auth_type, tab=tab_for_auth_type(auth_type), api_key_env_vars=api_key_vars,
                base_url_env_var=base_url_var, signup_url=signup_url, order=order,
                keyless=bool(overlay.keyless) if overlay else False,
            )
        )
    return out


def provider_catalog_by_slug() -> dict[str, ProviderDescriptor]:
    """Convenience: the catalog keyed by slug."""
    return {d.slug: d for d in provider_catalog()}
