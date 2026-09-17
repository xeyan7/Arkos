"""Secret-scrub policy for Arkos child processes: pure data + predicates for which env
names are Arkos-managed credentials. The env *builders* applying it (``_make_run_env``,
``_sanitize_subprocess_env``, ``arkos_subprocess_env``) live in ``tools.environments.local``."""

import os

_ARKOS_PROVIDER_ENV_FORCE_PREFIX = "_ARKOS_FORCE_"

_AWS_SDK_CREDENTIAL_ENV_VARS = frozenset({"AWS_BEARER_TOKEN_BEDROCK"})

_STATIC_PROVIDER_ENV_BLOCKLIST = frozenset({
    "OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_API_BASE", "OPENAI_ORG_ID",
    "OPENAI_ORGANIZATION", "OPENROUTER_API_KEY", "ANTHROPIC_BASE_URL",
    "ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN", "LLM_MODEL", "GOOGLE_API_KEY",
    "VERTEX_CREDENTIALS_PATH", "GOOGLE_APPLICATION_CREDENTIALS", "DEEPSEEK_API_KEY",
    "MISTRAL_API_KEY", "GROQ_API_KEY", "TOGETHER_API_KEY", "PERPLEXITY_API_KEY",
    "COHERE_API_KEY", "FIREWORKS_API_KEY", "XAI_API_KEY", "HELICONE_API_KEY",
    "PARALLEL_API_KEY", "FIRECRAWL_API_KEY", "FIRECRAWL_API_URL",
    "TELEGRAM_HOME_CHANNEL", "TELEGRAM_HOME_CHANNEL_NAME", "DISCORD_HOME_CHANNEL",
    "DISCORD_HOME_CHANNEL_NAME", "DISCORD_REQUIRE_MENTION",
    "DISCORD_FREE_RESPONSE_CHANNELS", "DISCORD_AUTO_THREAD", "SLACK_HOME_CHANNEL",
    "SLACK_HOME_CHANNEL_NAME", "SLACK_ALLOWED_USERS", "WHATSAPP_ENABLED",
    "WHATSAPP_MODE", "WHATSAPP_ALLOWED_USERS", "SIGNAL_HTTP_URL", "SIGNAL_ACCOUNT",
    "SIGNAL_ALLOWED_USERS", "SIGNAL_GROUP_ALLOWED_USERS", "SIGNAL_HOME_CHANNEL",
    "SIGNAL_HOME_CHANNEL_NAME", "SIGNAL_IGNORE_STORIES", "HASS_TOKEN", "HASS_URL",
    "EMAIL_ADDRESS", "EMAIL_PASSWORD", "EMAIL_IMAP_HOST", "EMAIL_SMTP_HOST",
    "EMAIL_HOME_ADDRESS", "EMAIL_HOME_ADDRESS_NAME", "ARKOS_DASHBOARD_SESSION_TOKEN",
    "GATEWAY_ALLOWED_USERS", "GH_TOKEN", "GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY_PATH",
    "GITHUB_APP_INSTALLATION_ID", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET",
    "DAYTONA_API_KEY", "GATEWAY_RELAY_ID", "GATEWAY_RELAY_SECRET",
    "GATEWAY_RELAY_DELIVERY_KEY", "VERCEL_OIDC_TOKEN", "VERCEL_TOKEN",
    "VERCEL_PROJECT_ID", "VERCEL_TEAM_ID",
})


def _build_provider_env_blocklist() -> frozenset:
    """Derive the blocklist from provider, tool, and gateway config."""
    blocked: set[str] = set(_STATIC_PROVIDER_ENV_BLOCKLIST)
    try:
        from arkos_cli.auth import PROVIDER_REGISTRY
        for pconfig in PROVIDER_REGISTRY.values():
            blocked.update(pconfig.api_key_env_vars)
            if pconfig.auth_type == "aws_sdk":
                blocked.update(_AWS_SDK_CREDENTIAL_ENV_VARS)
            if pconfig.base_url_env_var:
                blocked.add(pconfig.base_url_env_var)
    except ImportError:
        pass
    try:
        from arkos_cli.config import OPTIONAL_ENV_VARS
        for name, metadata in OPTIONAL_ENV_VARS.items():
            category = metadata.get("category")
            if category in {"tool", "messaging"} or (
                    category == "setting" and metadata.get("password")):
                blocked.add(name)
    except ImportError:
        pass
    blocked.discard("CLAUDE_CODE_OAUTH_TOKEN")
    return frozenset(blocked)


_ARKOS_PROVIDER_ENV_BLOCKLIST = _build_provider_env_blocklist()

_TERMINAL_FIRST_PARTY_ENV_PREFIXES = ("BUZZ_",)


def _matches_terminal_first_party_prefix(name: str) -> bool:
    """Pure name check (``BUZZ_*``), regardless of session context — the snapshot
    exclusion must stay conservative even when the carve-out is inactive."""
    return name.startswith(_TERMINAL_FIRST_PARTY_ENV_PREFIXES)


def _buzz_terminal_context_active() -> bool:
    """True when this process/session operates as a Buzz agent: ``BUZZ_MANAGED_AGENT`` in
    the process env (set only by Buzz Desktop's buzz-acp harness), or the live session's
    platform is ``buzz`` via the gateway ContextVar — authoritative under a concurrent
    multi-session host, so a sibling Telegram session resolves its OWN platform.

    Gateway / CLI / cron / kanban processes never carry it..
    """
    if os.environ.get("BUZZ_MANAGED_AGENT"):
        return True
    try:
        from gateway.session_context import get_session_env

        return get_session_env("ARKOS_SESSION_PLATFORM", "").strip().lower() == "buzz"
    except Exception:
        return False


def _is_terminal_first_party_env(name: str) -> bool:
    """``name`` is a first-party platform credential (``BUZZ_*``) AND the current
    process/session context entitles it to reach terminal children."""
    return _matches_terminal_first_party_prefix(name) and _buzz_terminal_context_active()


_ACTIVE_VENV_MARKER_VARS = ("VIRTUAL_ENV", "CONDA_PREFIX", "PYTHONHOME")


def _is_arkos_internal_secret(key: str) -> bool:
    """True for Arkos-internal secrets injected under *dynamic* names the static
    blocklist cannot enumerate: ``AUXILIARY_<TASK>_API_KEY``/``_BASE_URL`` (per-task
    side-LLM credentials) and ``GATEWAY_RELAY_*_SECRET``/``_KEY``/``_TOKEN`` (relay
    auth; non-secret routing hints stay visible). Stripped on every spawn path
    regardless of env_passthrough registration or ``inherit_credentials``."""
    upper = key.upper()
    if upper.startswith("AUXILIARY_") and upper.endswith(("_API_KEY", "_BASE_URL")):
        return True
    return upper.startswith("GATEWAY_RELAY_") and upper.endswith(("_SECRET", "_KEY", "_TOKEN"))


def _plugin_terminal_env_strip_keys() -> frozenset:
    """Credential env keys owned by plugin-registered terminal backends (Tier-1:
    stripped from every spawned subprocess). Computed at call time because plugins
    register after import; fail-soft to empty."""
    try:
        from agent.terminal_env_registry import plugin_strip_env_keys

        return plugin_strip_env_keys()
    except Exception:
        return frozenset()


_ALWAYS_STRIP_KEYS: frozenset[str] = frozenset({
    "GH_TOKEN", "GITHUB_TOKEN", "GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY_PATH",
    "GITHUB_APP_INSTALLATION_ID",
    "TELEGRAM_BOT_TOKEN", "DISCORD_BOT_TOKEN", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN",
    "SLACK_SIGNING_SECRET", "GATEWAY_ALLOWED_USERS", "GATEWAY_ALLOW_ALL_USERS",
    "GATEWAY_RELAY_ID", "GATEWAY_RELAY_SECRET", "GATEWAY_RELAY_DELIVERY_KEY",
    "HASS_TOKEN", "EMAIL_PASSWORD", "ARKOS_DASHBOARD_SESSION_TOKEN",
    "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "DAYTONA_API_KEY",
})
