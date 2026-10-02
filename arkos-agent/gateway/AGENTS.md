# gateway/ — Gateway Engine Plumbing

Applies on top of the root `AGENTS.md`.

## Overview

The `gateway/` package provides core backend engine plumbing for session context,
message delivery routing, and runtime lifecycle.

> **Engine build note:** All interactive frontend messaging platform adapters
> (Telegram, Slack, Discord, WhatsApp, Signal, etc.) and the gateway relay were removed
> in the engine-only build. `gateway/` operates strictly as an engine plumbing library.

## Key Modules

- **`session_context.py`**: ContextVars-based ambient session context (`set_current_session_id`,
  `get_current_session_id`, `scoped_current_session_id`). Ensures background tasks and
  subagent turns resolve the appropriate session identity without cross-talk.
- **`delivery.py`**: Resolves target routing (`DeliveryTarget`, `DeliveryTransport`) for
  cron jobs and autonomous notifications. Integrates with `dead_targets.py` to prevent repeated
  delivery attempts to confirmed-dead targets.
- **`dead_targets.py`**: Persistent registry of delivery targets confirmed unreachable.
- **`config.py` & `config_loader.py`**: Gateway configuration schemas (`GatewayConfig`, `PlatformConfig`).
- **`restart.py`**: Coordinated graceful restart and drain logic for running processes.
- **`shutdown_watchdog.py`**: Monitors process lifecycle and ensures unhandled stalls or zombie tasks terminate cleanly.
- **`media_repair.py` & `media_policy.py`**: Media handling, inspection, and local attachment policies.
- **`browser_control_broker.py`**: In-process broker for CDP-based browser control sessions.
- **`channel_directory.py` & `profile_routing.py`**: In-memory channel directory and profile-based message routing.

*Part of Arkos, an AI agent engine.*
