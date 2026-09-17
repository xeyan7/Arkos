# Arkos CLI Reference (Arkos Engine)

Live sources when anything looks stale: `arkos --help`, `arkos <command> --help`,


### Global Flags

```
arkos [flags] [command]        (no subcommand = interactive chat)

  --version, -V             Show version
  -z, --oneshot PROMPT      One-shot: print ONLY the final response (for scripts/pipes)
  -m MODEL  --provider P    Model/provider override for this invocation
  -t, --toolsets LIST       Comma-separated toolsets for this invocation
  --resume, -r SESSION      Resume session by ID or title
  --continue, -c [NAME]     Resume by name, or most recent session
  --worktree, -w            Isolated git worktree mode (parallel agents)
  --skills, -s SKILL        Preload skills (comma-separate or repeat)
  --profile, -p NAME        Use a named profile
  --yolo                    Skip dangerous command approval
  --tui / --cli             Force the Ink TUI / classic REPL
  --ignore-rules            Skip AGENTS.md/SOUL.md/memory/skill injection
  --safe-mode               Disable ALL customizations (troubleshooting)
  --pass-session-id         Include session ID in system prompt
```

### Chat

```
arkos chat [flags]
  -q, --query TEXT          Single query, non-interactive
  --image PATH              Attach a local image to a single query
  -Q, --quiet               Suppress banner, spinner, tool previews
  --checkpoints             Enable filesystem checkpoints (/rollback)
  --max-turns N             Cap tool-calling iterations
  --source TAG              Session source tag (default: cli)
```
(plus the global flags above)

### Configuration

```
arkos setup [section]      Wizard (model|tts|terminal|gateway|tools|agent)
arkos model                Interactive model/provider picker
arkos fallback [add|remove|list]  Fallback provider chain
arkos config [show|edit|get|set|unset|path|env-path|check|migrate]
arkos login / logout       OAuth sign-in / clear stored auth
arkos doctor [--fix]       Check dependencies and config
arkos status [--all]       Component status
```

### Tools & Skills

```
arkos tools [list|enable NAME|disable NAME]   Per-platform toolsets (curses UI with no args)

arkos skills list|browse|search QUERY|inspect ID
arkos skills install ID    Hub identifier OR a direct https://…/SKILL.md URL
arkos skills config        Enable/disable skills per platform
arkos skills check|update|uninstall|publish PATH
arkos skills tap add REPO  Add a GitHub repo as a skill source
arkos bundles              Skill bundles (one /<name> alias loads several skills)
```

### MCP Servers

```
arkos mcp add NAME (--url or --command) | remove | list | test NAME
arkos mcp catalog | install NAME     Curated catalog install
arkos mcp configure NAME             Toggle tool selection
arkos mcp serve                      Run the agent as an MCP server
```
Details (transport, tool discovery, catalog): `references/native-mcp.md`.

### Gateway (Messaging Platforms)

```
arkos gateway run|install|start|stop|restart|status|setup
```

20+ platforms: Telegram, Discord, Slack, WhatsApp (Baileys + Business Cloud API), iMessage (Photon — `arkos photon setup`), Signal, Email, SMS, Matrix, Mattermost, Teams, LINE, SimpleX, ntfy, Google Chat, Home Assistant, DingTalk, Feishu, WeCom, Weixin, API Server, Webhooks. Open WebUI connects via the API Server adapter. Most adapters ship under `plugins/platforms/`.
Docs:

### Sessions

```
arkos sessions list|browse|rename ID TITLE|delete ID|export OUT|prune|stats
```

### Cron / Webhooks

```
arkos cron list|create SCHED|edit ID|pause|resume|run ID|remove|status
    Schedules: '30m', 'every 2h', '0 9 * * *', ISO timestamp
arkos webhook subscribe NAME|list|remove NAME|test NAME
```
Webhook payloads/routes: `references/webhooks.md`.

### Profiles

```
arkos profile list|create NAME (--clone|--clone-all|--clone-from)|use|show|delete
arkos profile rename A B | alias NAME | export NAME | import FILE
```

### Credentials & Pools

```
arkos auth                 Interactive credential manager
arkos auth add [PROVIDER]  Add OAuth or API-key credential (openai-codex, qwen-oauth, …)
arkos auth list|remove P IDX|reset PROVIDER|status
```
Multiple credentials per provider form a pool that rotates automatically and skips exhausted keys.

### Other

```
arkos desktop / gui        Native desktop app
arkos dashboard            Web admin panel + embedded chat (--stop / --status)
arkos proxy                OpenAI-compatible local proxy backed by an OAuth provider
arkos portal               Quick setup / sign in via the portal
arkos kanban <verb>        Multi-agent work-queue board
arkos project              Named multi-folder workspaces
arkos skin list|use|set    Switch/tweak skins (see references/themes.md)
arkos pets <verb>          Pet mascots (see references/petdex.md)
arkos memory setup|status|off|reset   Memory provider
arkos secrets bitwarden|onepassword   External secret stores
arkos moa                  Mixture-of-Agents slots
arkos hooks / security / backup / import / checkpoints / console
arkos logs [-f] [errors]   View agent/error logs
arkos send                 One-off message through a gateway platform
arkos pairing / plugins / insights / journey / computer-use
arkos acp                  ACP server (IDE integration)
arkos completion bash|zsh|fish
arkos update / uninstall / legacy migrate
```

Plugin- and provider-supplied subcommands (e.g. `arkos photon setup`) only appear once their plugin is installed/active.

### Where to Find Things

| Looking for... | Location |
|---|---|
| Config options | `arkos config edit` · Configuration docs |
| Tools / toolsets | `arkos tools list` · Tools reference |
| Skills catalog | `arkos skills browse` · Skills catalog |
| Provider setup | `arkos model` · Providers guide |
| Env variables | `arkos config env-path` · Env vars reference |
| Gateway logs | `~/.arkos/logs/gateway.log` (or `arkos logs`) |
| Sessions | `arkos sessions browse` (reads state.db) |

*Part of Arkos, an AI agent engine.*
