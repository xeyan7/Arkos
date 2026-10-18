# Arkos Agent Engine

Arkos is a private AI agent engine maintained for its owner's use. This
checkout contains the engine, configuration libraries, tools, plugins, and
bundled skills. Access and distribution are controlled by the project owner.

The engine supports tool calling, persistent memory, reusable skills,
scheduled jobs, delegated tasks, and multiple model providers. The current
engine build does not include interactive CLI, desktop, or messaging
frontends.

## Owner setup

From an authorized local checkout, install the dependencies:

```bash
cd arkos-agent
uv pip install -e ".[all]"
```

For development dependencies, use `uv pip install -e ".[all,dev]"`.
The project requires Python 3.11 through 3.13. Configure credentials in
the profile's `.env` and behavior in `config.yaml`; do not commit secrets.

## Engine use

```python
from run_agent import AIAgent

agent = AIAgent(model="claude-3-5-sonnet")
response = agent.run_conversation("Check system status and summarize findings.")
print(response)
```

## Embedding in a future UI

Use `AIAgent.run_conversation()` with stream, tool-start, tool-complete, thinking, status, and event callbacks. Clients own visual rendering. Approval and sudo-password collection require host callbacks; missing approval callbacks deny dangerous operations. Profile deletion requires explicit `yes=True`. Dependency installation still obeys `security.allow_lazy_installs` and never opens a terminal menu.

`arkos_cli` is a backend namespace for configuration, authentication, profiles, and provider discovery. Its name does not imply an installed Arkos CLI. Optional web-server dependencies remain in the `web` extra for future API hosts.

## Internal development guides

- [AGENTS.md](AGENTS.md) — Engine design invariants and internal change standards
- [agent/AGENTS.md](agent/AGENTS.md) — Agent loop, caching, compression, and model resolution
- [arkos_cli/AGENTS.md](arkos_cli/AGENTS.md) — Configuration, authentication, and profiles
- [tools/AGENTS.md](tools/AGENTS.md) — Tool registry and execution backends
- [gateway/AGENTS.md](gateway/AGENTS.md) — Session context and engine plumbing
- [cron/AGENTS.md](cron/AGENTS.md) — Scheduler and jobs
- [plugins/AGENTS.md](plugins/AGENTS.md) — Plugin architecture and lifecycle
- [skills/AGENTS.md](skills/AGENTS.md) — Bundled skill format and maintenance

These guides support internal maintenance. Changes and releases are
authorized by the project owner.

## Distribution terms

See [LICENSE](LICENSE) for private distribution terms and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for inherited and third-party
license information. Private project status does not replace the licenses
that apply to those components.

Package metadata marks this checkout `Private :: Do Not Upload` to prevent
accidental publication to PyPI. Repository access is configured separately
on the hosting service; local metadata does not change hosted visibility.
