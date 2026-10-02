# Arkos Agent Engine

**Autonomous AI agent engine with tool-calling capabilities.** Arkos executes tasks autonomously across system environments. It has a built-in learning loop — creating skills from experience, persisting knowledge, searching past conversations, and remembering preferences across sessions. Run it on a local machine, a VPS, or a GPU cluster.

Use any model you want — OpenRouter, OpenAI, Anthropic, or local endpoints — with no lock-in.

<table>
<tr><td><b>A closed learning loop</b></td><td>Agent-curated memory with periodic nudges. Autonomous skill creation after complex tasks. Skills self-improve during use. FTS5 session search with LLM summarization for cross-session recall. Dialectic user memory modeling. Built-in skills ecosystem compatible with open agent skill specifications.</td></tr>
<tr><td><b>Scheduled automations</b></td><td>Built-in cron scheduler. Daily reports, nightly backups, weekly audits — all in natural language, running unattended.</td></tr>
<tr><td><b>Delegates and parallelizes</b></td><td>Spawn isolated subagents for parallel workstreams. Write Python scripts that call tools via RPC, collapsing multi-step pipelines into zero-context-cost turns.</td></tr>
<tr><td><b>Runs anywhere</b></td><td>Pluggable execution backends — local, Docker, SSH, Singularity, Modal, Daytona, and Vercel Sandbox. Daytona and Modal offer serverless persistence — environments hibernate when idle and wake on demand.</td></tr>
<tr><td><b>Research-ready</b></td><td>Batch trajectory generation, trajectory compression for evaluation and offline benchmarking.</td></tr>
</table>

---

## Quick Install

### Linux, macOS, WSL2, Termux

Clone the repository and install dependencies:

```bash
git clone <repository-url>
cd arkos-agent
uv pip install -e ".[all]"
```

### Windows (native, PowerShell)

> **Heads up:** Native Windows runs the agent engine without WSL. MinGit/Git Bash is detected or provisioned automatically to run shell commands cleanly.

Clone the repository and install dependencies from PowerShell:

```powershell
git clone <repository-url>
cd arkos-agent
uv pip install -e ".[all]"
```

The installer or uv manages Python, dependencies, and environment configuration cleanly.

> **Android / Termux:** On Termux, install the curated `.[termux]` extra to avoid Android-incompatible voice dependencies.

---

## Getting Started

### Programmatic Usage

Run the agent engine directly in Python:

```python
from run_agent import AIAgent

# Initialize the agent with your target model
agent = AIAgent(model="claude-3-5-sonnet")

# Execute a conversation turn with tool calling
response = agent.run_conversation("Check system status and summarize findings.")
print(response)
```

### CLI / Script Invocation

You can also run batch trajectories or one-shot executions:

```bash
python run_agent.py
```

---

## Subsystem Architecture & Documentation

Each area of the engine contains a dedicated development guide:

- [AGENTS.md](AGENTS.md) — Root engine design invariants, caching rules, and contribution standards
- [agent/AGENTS.md](agent/AGENTS.md) — Agent loop, turn phases, caching integrity, compression, and model resolution
- [arkos_cli/AGENTS.md](arkos_cli/AGENTS.md) — Configuration system, auth, models, and profiles
- [tools/AGENTS.md](tools/AGENTS.md) — Tool registry, toolsets, delegation, and execution backends
- [gateway/AGENTS.md](gateway/AGENTS.md) — Session context, delivery routing, and engine plumbing
- [cron/AGENTS.md](cron/AGENTS.md) — Scheduler invariants and cron jobs
- [plugins/AGENTS.md](plugins/AGENTS.md) — Plugin architecture and lifecycle
- [skills/AGENTS.md](skills/AGENTS.md) — Skills format, frontmatter, and authoring standards

---

## Contributing

Quick start for developers working from a git checkout:

```bash
cd arkos-agent
uv pip install -e ".[all,dev]"
```

---

## License

MIT — see [LICENSE](LICENSE).

*Part of Arkos, an AI agent engine.*
