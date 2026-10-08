# Engine cleanup audit

This records the frontend cleanup. See [ENGINE_HEALTH_REVIEW.md](ENGINE_HEALTH_REVIEW.md) for subsequent repairs and current validation; the file inventory has been refreshed.

Scanned the starting working tree of **1377 files**, excluding Git history. Examined Python imports, call sites, dynamic tool/provider/plugin registrations, packaging, and documentation. Prior portal cleanup and other existing local changes were preserved.

## Removed frontend files

**35 old files removed or replaced**: 30 removed without a replacement module, and 5 mixed frontend/backend modules replaced by backend libraries.

| File | Reason / replacement |
|---|---|
| `arkos_cli/tools_config.py` | Backend extracted to `arkos_cli/tool_configuration.py`. Mixed frontend/library module replaced by a headless engine library. |
| `arkos_cli/tools_config_providers.py` | Backend extracted to `arkos_cli/tool_providers.py`. Mixed frontend/library module replaced by a headless engine library. |
| `arkos_cli/tools_config_post_setup.py` | Backend extracted to `arkos_cli/tool_dependencies.py`. Mixed frontend/library module replaced by a headless engine library. |
| `arkos_cli/tools_config_cua.py` | Backend extracted to `tools/cua_install.py`. Computer-use installer moved to the tools backend; no Arkos command menu remains. |
| `arkos_cli/main_provider_setup.py` | Interactive model/provider setup and numbered/curses menus. |
| `arkos_cli/model_setup_flows_common.py` | Terminal input and curses adapters for deleted setup flows. |
| `arkos_cli/auth_model_picker.py` | Interactive model picker; authentication does not need it. |
| `arkos_cli/tools_config_mcp.py` | Interactive MCP checklist and Arkos tool command dispatcher. |
| `arkos_cli/cron.py` | Arkos cron command UI; scheduler and cronjob tool are retained. |
| `arkos_cli/_early_recovery.py` | Recovery for an already-deleted CLI updater entrypoint. |
| `agent/battery.py` | Battery glyphs and terminal status bar. |
| `agent/onboarding.py` | Hints for deleted CLI/gateway onboarding. |
| `agent/markdown_tables.py` | Terminal Markdown-table rendering. |
| `agent/learning_graph_render.py` | Terminal rendering for learning graphs; graph storage remains. |
| `agent/lsp/cli.py` | Arkos LSP command dispatcher; LSP runtime remains. |
| `arkos_cli/local_runtime/hf_browse.py` | Interactive Hugging Face catalog browser; runtime/download backends remain. |
| `agent/pet/constants.py` | Frontend animated-pet rendering, assets, and generation; no engine consumer. |
| `agent/pet/manifest.py` | Frontend animated-pet rendering, assets, and generation; no engine consumer. |
| `agent/pet/render.py` | Frontend animated-pet rendering, assets, and generation; no engine consumer. |
| `agent/pet/state.py` | Frontend animated-pet rendering, assets, and generation; no engine consumer. |
| `agent/pet/store.py` | Frontend animated-pet rendering, assets, and generation; no engine consumer. |
| `agent/pet/__init__.py` | Frontend animated-pet rendering, assets, and generation; no engine consumer. |
| `agent/pet/generate/atlas.py` | Frontend animated-pet rendering, assets, and generation; no engine consumer. |
| `agent/pet/generate/imagegen.py` | Frontend animated-pet rendering, assets, and generation; no engine consumer. |
| `agent/pet/generate/orchestrate.py` | Frontend animated-pet rendering, assets, and generation; no engine consumer. |
| `agent/pet/generate/prompts.py` | Frontend animated-pet rendering, assets, and generation; no engine consumer. |
| `agent/pet/generate/__init__.py` | Frontend animated-pet rendering, assets, and generation; no engine consumer. |
| `plugins/memory/mem0/_setup.py` | Interactive memory-provider setup wizard; provider runtime kept. |
| `plugins/memory/openviking/_setup.py` | Interactive memory-provider setup wizard; provider runtime kept. |
| `plugins/memory/hindsight/setup.py` | Interactive memory-provider setup wizard; provider runtime kept. |
| `agent/display.py` | Backend extracted to `agent/tool_feedback.py`. Mixed frontend/library module replaced by a headless engine library. |
| `plugins/memory/honcho/cli.py` | Interactive Honcho setup and terminal commands; memory runtime stays. |
| `plugins/teams_pipeline/cli.py` | Operator CLI registration; Teams pipeline backend modules retained. |
| `plugins/teams_pipeline/plugin.yaml` | Operator CLI registration; Teams pipeline backend modules retained. |
| `arkos_cli/secret_prompt.py` | Terminal password masking; host credential APIs retained. |

## Changes inside retained files

Removed the standalone agent command runner; login/logout/config/backup command dispatchers; numbered setup flows; terminal spinners and delegate tree rendering; terminal password collection; and profile/approval/dependency confirmation prompts. Stale compatibility pointers to absent modules were removed. Documentation for removed skin/update/kanban frontends was cleaned up.

Configuration, provider catalogs, provider selection, authentication protocols, memory providers, database persistence, tools, delegation, scheduler workers, and callback/event APIs remain. `arkos_cli` remains a backend namespace: deleting it would break engine imports.

Dangerous-operation approvals deny when no host callback is supplied. Sudo password collection skips without a host callback. Profile deletion requires explicit `yes=True`. Unapproved shell hooks are denied. Anthropic PKCE login requires `authorization_callback(auth_url)`; CSRF validation remains. OAuth device-code/loopback protocols and existing-profile credential reuse remain. Explicit dependency consent and `security.allow_lazy_installs` still apply.

Removed Fire, prompt-toolkit and pathspec from core dependencies; removed dashboard FastAPI/uvicorn/multipart requirements from core. Optional web hosting dependencies remain in the `web` extra. Regenerated `uv.lock` and verified it with `uv lock --check --offline`.

## File categories

Every starting file, removed file, and newly added source module is listed in [engine_file_inventory.json](engine_file_inventory.json), with categories, deletion reasons, replacement paths, and direct importers where applicable. Counts below include starting files plus added backend files.

| Category | Files |
|---|---:|
| Packaging, documentation and legal notices | 17 |
| Engine core and orchestration | 270 |
| Configuration, authentication, profiles and provider discovery | 114 |
| Database and session storage | 22 |
| Scheduling and durable jobs | 23 |
| Session routing and delivery integration | 22 |
| Localization catalogs | 17 |
| Native runtime extensions | 5 |
| Optional MCP integrations | 64 |
| Skills and feature assets | 356 |
| Provider and extension backends | 219 |
| Model provider profiles | 3 |
| Maintenance and validation scripts | 8 |
| Tool execution and external integrations | 247 |

## Retained modules without static root reachability

These are **review candidates, not proven dead files**. Tools are loaded by string names in `model_tools`, providers/transports are registered dynamically, and embedding hosts can call exported APIs. Curator, hooks, telemetry, verification/review, learning graphs, one-shot/side-question, skills synchronization, voice/video, secret-source adapters and MCP serving are backend capabilities. They were retained to avoid deleting features needed by a future UI.

- `agent.account_usage`
- `agent.compaction_display`
- `agent.credential_sources`
- `agent.curator`
- `agent.curator_backup`
- `agent.error_surface`
- `agent.i18n`
- `agent.insights`
- `agent.learning_graph`
- `agent.learning_mutations`
- `agent.manual_compression_feedback`
- `agent.monitoring.gateway_health_export`
- `agent.monitoring.otlp_exporter`
- `agent.monitoring.policy`
- `agent.oneshot`
- `agent.outbound_webhooks`
- `agent.replay_cleanup`
- `agent.review_engine`
- `agent.secret_sources.command`
- `agent.secret_sources.onepassword`
- `agent.shell_hooks`
- `agent.side_question`
- `agent.stream_diag`
- `agent.trace_upload`
- `agent.transports.anthropic`
- `agent.transports.arkos_tools_mcp_server`
- `agent.transports.bedrock`
- `agent.tts_provider`
- `agent.tts_registry`
- `agent.turn_summary`
- `agent.verify`
- `agent.verify.runner`
- `agent.video_gen_registry`
- `arkos_cli.local_runtime`
- `arkos_cli.observability.relay_runtime`
- `arkos_cli.prompt_size`
- `cron.suggestions`
- `gateway.builtin_hooks`
- `setup`
- `tools.audio_container`
- `tools.browser_cdp_tool`
- `tools.browser_dialog_tool`
- `tools.clarify_tool`
- `tools.computer_use.permissions`
- `tools.computer_use_tool`
- `tools.mcp_death_supervisor`
- `tools.neutts_synth`
- `tools.openrouter_client`
- `tools.session_search_tool`
- `tools.skills_hub`
- `tools.skills_hub_clawhub`
- `tools.skills_hub_github`
- `tools.skills_hub_install`
- `tools.skills_hub_models`
- `tools.skills_hub_official`
- `tools.skills_hub_search`
- `tools.skills_hub_skillssh`
- `tools.skills_hub_sources`
- `tools.skills_sync`
- `tools.skills_sync_bundled_ops`
- `tools.skills_sync_optional`
- `tools.tts_streaming`
- `tools.tts_text_normalize`
- `tools.tts_tool`
- `tools.tts_tool_delivery`
- `tools.tts_tool_lifecycle`
- `tools.tts_tool_local`
- `tools.tts_tool_openai`
- `tools.tts_tool_plugins`
- `tools.tts_tool_providers`
- `tools.tts_tool_speaker`
- `tools.video_generation_tool`
- `tools.voice_mode`
- `tools.voice_mode_transcript`
- `tools.x_search_tool`
- `tools.xai_video_tools`

## Remaining integration gaps from earlier slimming

The scan still finds imports to the modules below. These were already absent at the start of this task. Many imports are guarded fallbacks or optional delivery paths, so this list is **not a claim that each importer fails on startup**. It identifies paths that need a real host implementation or targeted replacement before that feature can be used. Missing old-schema configuration migration, legacy model-picker/catalog helpers, plugin command/platform registries, and messaging delivery adapters are particularly relevant. Required engine files were retained; deleting them merely because an optional branch is incomplete would remove backend capabilities.

| Absent module | Referencing modules |
|---|---|
| `arkos_cli.agent_plugins` | `arkos_cli.plugins`, `arkos_cli.plugins_loader`, `arkos_cli.plugins_manifest` |
| `arkos_cli.build_info` | `gateway.status` |
| `arkos_cli.commands` | `agent.skill_commands`, `arkos_cli.plugins`, `plugins.context_engine` |
| `arkos_cli.config_migrations` | `arkos_cli.config` |
| `arkos_cli.dashboard_procs` | `arkos_state_gateway` |
| `arkos_cli.gateway` | `arkos_cli.backup`, `arkos_cli.profiles` |
| `arkos_cli.main` | `gateway.code_skew` |
| `arkos_cli.model_catalog` | `arkos_cli.models` |
| `arkos_cli.model_search` | `arkos_cli.models` |
| `arkos_cli.model_switch` | `agent.agent_init`, `arkos_cli.models` |
| `arkos_cli.model_switch_providers` | `arkos_cli.models` |
| `arkos_cli.platform_actions` | `arkos_cli.plugins` |
| `arkos_cli.service_manager` | `arkos_cli.profiles` |
| `arkos_cli.toolset_validation` | `arkos_cli.config` |
| `gateway.config_env` | `gateway.config` |
| `gateway.display_config` | `arkos_cli.config` |
| `gateway.lifecycle_ledger` | `arkos_startup_watchdog`, `gateway.shutdown_watchdog` |
| `gateway.platforms` | `tools.send_message_senders` |
| `gateway.platforms.base` | `cron.scheduler_delivery`, `gateway.dead_targets`, `gateway.media_repair`, `tools.mcp_tool_content`, `tools.send_message_senders`, `tools.send_message_tool`, `tools.skills_tool_setup` |
| `gateway.platforms.signal` | `tools.send_message_tool` |
| `gateway.platforms.signal_format` | `tools.send_message_senders` |
| `gateway.platforms.yuanbao` | `tools.send_message_senders` |
| `gateway.relay` | `cron.scheduler_delivery`, `tools.cronjob_tools` |
| `gateway.relay.egress` | `tools.send_message_tool` |
| `gateway.run` | `agent.relay_runtime`, `tools.send_message_senders` |
| `gateway.session` | `cron.scheduler_delivery` |
| `gateway.whatsapp_identity` | `gateway.profile_routing` |

## Verification

- Parsed and compiled **953 Python files**; parsed JSON, TOML, and **159 YAML files**. No Python syntax errors.
- Baseline-aware undefined-global and removed-module import checks: zero new issues.
- **10 offline regression tests passed**: agent initialization, direct-provider discovery/routing, third-party pricing, audio/browser request configuration, request scopes, session storage, tool provider selection, callback-only approvals/sudo, host-only OAuth and delegated progress, and a complete model/tool/model turn.
- Real tool execution uses the deferred `tool_call` bridge and `todo_list`, preserving message order and byte-identical system messages across both requests. Provider HTTP responses are mocked; tools and the agent loop are real.
- Tests isolate `ARKOS_HOME` and `Path.home`, block network calls, and disable lazy installation. Reproduce with `python scripts/verify_engine_cleanup.py` on Python 3.11–3.13 with engine dependencies installed.
- Validation used supported Python **3.12.14**, OpenAI **2.24.0** and a small test dependency environment. Python 3.14 on the host failed the pre-existing daemon executor compatibility path; the project explicitly excludes 3.14, so that was not treated as a cleanup regression.
- Live vendor services, optional transports, native builds, long-running schedules and every external plugin were not exercised. No full original test suite is present in this slim checkout.
- Git history was left unchanged. Changes are local; this task did not publish them.
