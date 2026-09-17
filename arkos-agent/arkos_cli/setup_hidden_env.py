"""Which platform env vars the setup surfaces hide.

Hiding is a *presentation* decision only: the vars keep working through ``arkos config set``,
``.env`` and ``config.yaml``, and the gateway reads them exactly as before.
"""

SETUP_HIDDEN_ENV_SUFFIXES = (
    "_HOME_CHANNEL", "_HOME_CHANNEL_NAME", "_HOME_CHANNEL_THREAD_ID", "_HOME_ADDRESS", "_ALLOW_ALL_USERS",
    "_REPLY_TO_MODE", "_REPLY_MODE", "_REQUIRE_MENTION", "_AUTO_THREAD", "_FREE_RESPONSE_CHANNELS",
    "_FREE_RESPONSE_ROOMS", "_ALLOWED_CHANNELS", "_PROXY",
)


def is_setup_hidden_env(name: str) -> bool:
    """True when a var is self-configuring and shouldn't appear in setup forms. Callers must still
    keep any var a platform lists as *required* — hiding a required credential would make that
    platform unconfigurable from the UI."""
    return name.endswith(SETUP_HIDDEN_ENV_SUFFIXES)
