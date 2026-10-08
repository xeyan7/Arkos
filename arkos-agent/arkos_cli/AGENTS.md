# Engine configuration libraries

The `arkos_cli` namespace is retained because the engine imports it. It contains backend configuration, authentication, provider discovery, dependency recovery, profile isolation, and plugin management; it has no Arkos command entrypoint.

`tool_configuration.py` owns toolset policy; `tool_providers.py` owns catalogs and selection; `tool_dependencies.py` owns readiness metadata. Computer-use installation lives in `tools/cua_install.py`. Built-in auxiliary task metadata lives in `agent/auxiliary_tasks.py`.

Embedding hosts collect credentials and confirmations. Engine functions must not open menus or read stdin. OAuth device-code/loopback protocols remain authentication backends; a host supplies presentation.

## Config system (`arkos_cli/config.py`)

- **config.yaml option:** add to `DEFAULT_CONFIG`. Bump `_config_version` ONLY to actively
  migrate/transform existing config (rename keys, restructure); new keys deep-merge automatically.
  Top-level sections (non-exhaustive): `model, agent, terminal, compression, display, stt, tts,
  memory, security, delegation, smart_model_routing, checkpoints, auxiliary, curator, skills,
  gateway, logging, cron, profiles, plugins, honcho`. `auxiliary` = per-task side-LLM overrides
  (`agent/AGENTS.md`); `curator` = `enabled, interval_hours, min_idle_hours, stale_after_days,
  archive_after_days, backup.*`.
- **.env = SECRETS ONLY** (keys, tokens, passwords): add to `OPTIONAL_ENV_VARS` with
  `{"description", "prompt", "url", "password": True, "category": provider|tool|messaging|setting}`.
  Non-secret settings go in config.yaml; if internal code needs an env mirror, bridge it in code
  (`gateway_timeout`; `terminal.cwd` → `TERMINAL_CWD`). `MESSAGING_CWD` is removed and `TERMINAL_CWD`
  in `.env` is deprecated — the loader warns; canonical is `terminal.cwd`.
- **Three loaders — know which you're in:** `load_config()`
  (`arkos_cli/config.py`, merges `DEFAULT_CONFIG`); raw
  YAML (gateway runtime, `gateway/config.py`). (Engine build: `load_cli_config()`/`cli.py` and
  `gateway/run.py` deleted.) If the CLI sees a key and the
  gateway doesn't (or vice versa), you're on the wrong loader — check `DEFAULT_CONFIG` coverage.
- **Working directory:** CLI uses `os.getcwd()`; messaging uses `terminal.cwd`, bridged to
  `TERMINAL_CWD` for child tools.

## Profiles (multi-instance)

`get_arkos_home()` scopes to the active profile (rules in root). (Engine build:
profile override is applied before any module import; `arkos_cli/main.py` deleted.) Profiles are independent
islands by design — no live config inheritance; `--clone` copies at creation. Multiplex
(`gateway.multiplex_profiles`) secret-scope rules: `gateway/AGENTS.md`.

*Part of Arkos, an AI agent engine.*
