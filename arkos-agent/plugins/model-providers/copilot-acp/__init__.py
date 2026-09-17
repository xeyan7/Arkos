"""GitHub Copilot ACP provider profile.

copilot-acp does not speak OpenAI-over-HTTP: it drives an external ACP subprocess over
stdio, so the profile supplies its own client via :meth:`ProviderProfile.create_client`.
An out-of-tree ACP provider (``~/.arkos/plugins/model-providers/`` or a pip entry point)
uses the same three lines without touching core.
"""

from typing import Any

from providers import register_provider
from providers.base import ProviderProfile


class CopilotACPProfile(ProviderProfile):
    """GitHub Copilot ACP — external process, no REST models endpoint."""

    def create_client(self, **client_kwargs: Any) -> Any:
        """Build the ACP stdio shim rather than an HTTP client."""
        from agent.copilot_acp_client import CopilotACPClient

        return CopilotACPClient(**client_kwargs)

    def fetch_models(
        self, *, api_key: str | None = None, base_url: str | None = None, timeout: float = 8.0
    ) -> list[str] | None:
        """Model listing is handled by the ACP subprocess."""
        return None


copilot_acp = CopilotACPProfile(
    name="copilot-acp", aliases=("github-copilot-acp", "copilot-acp-agent"),
    api_mode="chat_completions",
    env_vars=(),
    base_url="acp://copilot",
    auth_type="external_process",
    process_command="copilot",
    process_args=("--acp", "--stdio"),
    process_command_env_vars=("ARKOS_COPILOT_ACP_COMMAND", "COPILOT_CLI_PATH"),
    process_args_env_var="ARKOS_COPILOT_ACP_ARGS",
)

register_provider(copilot_acp)
