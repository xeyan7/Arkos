"""OpenCode Free provider profile: the free tier on the Zen relay (https://opencode.ai/zen/v1).

KEYLESS: the relay serves free-tier models anonymously and 401s any bearer it
doesn't recognize, so this provider never sends a credential (the runtime
resolver pins the keyless placeholder and an empty Authorization header; see
arkos_cli.models.opencode_zen_free_runtime). Select via ``/model free``.
"""

from typing import Any

from arkos_cli import __version__ as _ARKOS_VERSION
from providers import register_provider
from providers.base import ProviderProfile


class OpenCodeFreeProfile(ProviderProfile):
    """OpenCode Free — keyless, with Ox Alpha reasoning controls.

    Ox Alpha (x-preview-f-free) is also reachable via opencode-zen with the same wire
    contract; the translation lives in the zen plugin and is resolved through the
    registered zen profile's module so the two providers can never drift.
    """

    def build_api_kwargs_extras(
        self, *, reasoning_config: dict | None = None, model: str | None = None, **context
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            import sys

            from providers import get_provider_profile

            zen_module = sys.modules[type(get_provider_profile("opencode-zen")).__module__]
            return zen_module._build_ox_alpha_reasoning_extras(reasoning_config, model)
        except Exception:
            return {}, {}


opencode_free = OpenCodeFreeProfile(
    name="opencode-free", aliases=("free", "opencode_free"),
    env_vars=(),
    base_url="https://opencode.ai/zen/v1", display_name="OpenCode Free",
    description="OpenCode free models — keyless, no account needed",
    default_headers={
        "Authorization": "",
        "HTTP-Referer": "https://arkos.local",
        "X-Title": "Arkos",
        "User-Agent": f"ArkosAgent/{_ARKOS_VERSION}",
    },
    default_aux_model="laguna-s-2.1-free",
)

register_provider(opencode_free)
