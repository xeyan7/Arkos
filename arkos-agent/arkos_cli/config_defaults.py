"""Default configuration data for Arkos: DEFAULT_CONFIG and OPTIONAL_ENV_VARS.

Pure-data leaf module — must not import from arkos_cli.config. Comments are the user-facing
docs of config.yaml.
"""


def _aux(timeout, *, reasoning_effort=True, **extra):
    """Standard auxiliary-task model block (see DEFAULT_CONFIG["auxiliary"]).

    reasoning_effort=False omits that key (MoA blocks configure depth per slot);
    ``extra`` keys are appended after the standard ones.
    """
    d = {"provider": "auto", "model": "", "base_url": "", "api_key": "", "timeout": timeout, "extra_body": {}}
    if reasoning_effort:
        d["reasoning_effort"] = ""
    d.update(extra)
    return d


DEFAULT_CONFIG = {
    "model": "",
    "providers": {},
    "fallback_providers": [],
    "credential_pool_strategies": {},
    "toolsets": ["arkos-cli"],
    "database": {
        "journal_mode": "wal",
        "wal_autocheckpoint": None,
        "journal_size_limit": None,
    },
    "runtime": {"nofile_soft_limit": 4096},
    "max_concurrent_sessions": None,
    "max_live_sessions": 16,
    "session": {
        "terminal_continue": True,
    },
    "agent": {
        "max_turns": None,
        "budget_warning_ratio": None,
        "run_budget_seconds": None,
        "gateway_timeout": 1800,
        "gateway_turn_lease_timeout": 5,
        "agent_cache": {
            "max_size": 128,
            "idle_ttl_secs": 3600,
            "memory_high_mb": "auto",
            "max_evictions_per_pass": 16,
            "protect_recent": 8,
        },
        "restart_drain_timeout": 0,
        "cron_drain_timeout": 30,
        "restart_after_turn_timeout": 1800,
        "build_wait_timeout": 600,
        "api_max_retries": 3,
        "empty_response_guard": {
            "enabled": True,
            "cost_threshold_usd": 0.25,
        },
        "service_tier": "",
        "fast_auto_seconds": 60,
        "tool_use_enforcement": "auto",
        "execution_guidance": "auto",
        "intent_ack_continuation": "auto",
        "stall_guards": True,
        "task_completion_guidance": True,
        "parallel_tool_call_guidance": True,
        "environment_probe": True,
        "bot_mode_protocol": True,
        "environment_hint": "",
        "coding_context": "auto",
        "coding_instructions": "",
        "verify_guidance": True,
        "max_verify_nudges": 3,
        "verify_on_stop": False,
        "gateway_timeout_warning": 900,
        "clarify_timeout": 3600,
        "gateway_notify_interval": 180,
        "session_stall_timeout": 300,
        "sanitizer_heal_escalation_threshold": 3,
        "reconnect_attention_after": 7200,
        "gateway_auto_continue_freshness": 3600,
        "gateway_startup_restore_drain_timeout": 30,
        "gateway_startup_warmup_timeout": 20,
        "local_stream_stale_timeout": 900,
        "image_input_mode": "auto",
        "disabled_toolsets": [],
        "reasoning_overrides": {},
        "reasoning_echo": False,
        "turn_liveness": {"timeout_s": 600.0, "poll_s": 15.0},
    },

    "terminal": {
        "backend": "local",
        "modal_mode": "auto",
        "degraded_mode": "warn",
        "cwd": ".",
        "temp_dir": "",
        "font_family": "",
        "timeout": 180,
        "daemon_term_grace_seconds": 2.0,
        "oneshot_completion_wait_seconds": 600.0,
        "env_passthrough": [],
        "home_mode": "auto",
        "shell_init_files": [],
        "auto_source_bashrc": True,
        "docker_image": "nikolaik/python-nodejs:python3.11-nodejs20",
        "docker_forward_env": [],
        "docker_env": {},
        "singularity_image": "docker://nikolaik/python-nodejs:python3.11-nodejs20",
        "modal_image": "nikolaik/python-nodejs:python3.11-nodejs20",
        "daytona_image": "nikolaik/python-nodejs:python3.11-nodejs20",
        "vercel_runtime": "node24",
        "container_cpu": 1,
        "container_memory": 5120,
        "container_disk": 51200,
        "container_persistent": True,
        "docker_volumes": [],
        "docker_mount_cwd_to_workspace": False,
        "docker_network": True,
        "docker_extra_args": [],
        "docker_shm_size": "1g",
        "docker_run_as_host_user": False,
        "docker_snap_compat": False,
        "docker_shared_container_key": "",
        "persistent_shell": True,
    },

    "web": {
        "backend": "",
        "search_backend": "",
        "extract_backend": "",
        "extract_char_limit": 15000,
        "keyless_fallback": True,
        "keyless_rescue": True,
        "provider_tier": {},
        "cache_enabled": True,
        "cache_ttl_minutes": 20,
        "cache_exempt_hosts": [],
    },

    "browser": {
        "backend": "",
        "inactivity_timeout": 120,
        "command_timeout": 30,
        "snapshot_threshold": 15000,
        "record_sessions": False,
        "headed": False,
        "allow_private_urls": False,
        "engine": "auto",
        "auto_local_for_private_urls": True,
        "cdp_url": "",
        "use_real_profile": False,
        "real_profile_autoclose": False,
        "real_profile_pin": "",
        "allow_unsafe_evaluate": False,
        "restrict_evaluate": False,
        "dialog_policy": "must_respond",
        "dialog_timeout_s": 300,
        "camofox": {
            "managed_persistence": False,
            "user_id": "",
            "session_key": "",
            "adopt_existing_tab": False,
            "rewrite_loopback_urls": False,
            "loopback_host_alias": "host.docker.internal",
        },
        "extension_control": {"enabled": False, "developer_mode": False},
    },
    "checkpoints": {
        "enabled": False,
        "max_snapshots": 20,
        "max_total_size_mb": 500,
        "max_file_size_mb": 10,
        "auto_prune": True,
        "retention_days": 7,
        "min_interval_hours": 24,
    },
    "context_file_max_chars": None,
    "context_file_read_timeout": 5.0,
    "file_read_max_chars": 100_000,
    "mcp_discovery_timeout": 1.5,
    "mcp_single_query_discovery_timeout": 15.0,
    "mcp": {
        "auto_reload_on_config_change": True,
    },
    "tool_output": {"max_bytes": 50000, "max_lines": 2000, "max_line_length": 2000},
    "tool_loop_guardrails": {
        "warnings_enabled": True,
        "hard_stop_enabled": False,
        "non_interactive_hard_stop_enabled": True,
        "warn_after": {"exact_failure": 2, "same_tool_failure": 3, "idempotent_no_progress": 2},
        "hard_stop_after": {
            "exact_failure": 5, "same_tool_failure": 8, "idempotent_no_progress": 5
        },
        "loop_caps": {
            "max_web_searches": 50,
            "max_subagents": 50,
        },
    },

    "compression": {
        "enabled": True,
        "checkpoint_required": False,
        "progress_notices": False,
        "threshold": 0.50,
        "threshold_tokens": None,
        "target_ratio": 0.20,
        "tail_mode": "lean",
        "protect_last_n": 20,
        "min_tail_user_messages": 1,
        "max_attempts": 3,
        "proactive_prune_tokens": 0,
        "proactive_prune_min_result_chars": 8000,
        "proactive_prune_min_reclaim_tokens": 4096,
        "micro_compact": False,
        "micro_compact_every_n_turns": 1,
        "micro_compact_defrag_threshold_tokens": 2000,
        "hygiene_hard_message_limit": 5000,
        "hygiene_timeout_seconds": 30,
        "hygiene_total_ceiling_seconds": 600,
        "hygiene_failure_cooldown_seconds": 300,
        "hygiene_max_turn_hold_seconds": 10,
        "context_timeout_seconds": 120,
        "context_total_ceiling_seconds": 600,
        "protect_first_n": 3,
        "abort_on_summary_failure": False,
        "codex_gpt55_autoraise": True,
        "codex_gpt55_autoraise_notice": True,
        "codex_app_server_auto": "native",
        "codex_responses_native": False,
        "codex_responses_compact_threshold": None,
        "in_place": True,
        "model_thresholds": {},
        "idle_compact_after_seconds": 0,
    },
    "prompt_caching": {"cache_ttl": "5m"},
    "openrouter": {"response_cache": True, "response_cache_ttl": 300, "min_coding_score": 0.65},
    "bedrock": {
        "region": "",
        "discovery": {
            "enabled": True,
            "provider_filter": [],
            "refresh_interval": 3600,
        },
        "guardrail": {
            "guardrail_identifier": "",
            "guardrail_version": "",
            "stream_processing_mode": "async",
            "trace": "disabled",
        },
    },
    "auxiliary": {
        "transient_retries": 2,
        "free_only": False,
        "openrouter_model": "",
        "stream_only_base_urls": [],
        "vision": _aux(120, download_timeout=30),
        "compression": _aux(120),
        "skills_hub": _aux(30),
        "approval": _aux(30),
        "review": {"provider": "auto", "model": "", "base_url": "", "api_key": "", "api_mode": ""},
        "mcp": _aux(30),
        "title_generation": {
            "enabled": True,
            "provider": "auto",
            "model": "",
            "prefer_fast_model": False,
            "base_url": "",
            "api_key": "",
            "timeout": 30,
            "extra_body": {},
            "reasoning_effort": "",
            "language": "",
        },
        "memory_query_rewrite": _aux(8, reasoning_effort=False),
        "tts_audio_tags": _aux(30),
        "triage_specifier": _aux(120),
        "kanban_decomposer": _aux(180),
        "profile_describer": _aux(60),
        "goal_judge": _aux(60),
        "curator": _aux(600),
        "monitor": _aux(60),
        "background_review": {"enabled": True, **_aux(120), "max_input_tokens": 600000},
        "moa_reference": _aux(900, reasoning_effort=False),
        "moa_aggregator": _aux(900, reasoning_effort=False),
    },

    "display": {
        "compact": False,
        "personality": "",
        "resume_display": "full",
        "resume_exchanges": 10,
        "resume_max_user_chars": 300,
        "resume_max_assistant_chars": 200,
        "resume_max_assistant_lines": 3,
        "resume_skip_tool_only": True,
        "busy_input_mode": "interrupt",
        "busy_steer_ack_enabled": True,
        "cli_multiline_shortcuts": True,
        "interface": "cli",
        "tui_auto_resume_recent": False,
        "resume_last_session": True,
        "tui_agents_nudge": True,
        "bell_on_complete": False,
        "bell_on_prompt": False,
        "show_reasoning": True,
        "reasoning_full": False,
        "memory_notifications": "on",
        "background_process_notifications": "concise",
        "streaming": False,
        "timestamps": False,
        "timestamp_format": "%H:%M",
        "final_response_markdown": "strip",
        "persistent_output": True,
        "persistent_output_max_lines": 200,
        "cli_rebuild_scrollback_on_redraw": False,
        "persist_prompts": True,
        "inline_diffs": True,
        "file_mutation_verifier": True,
        "credits_notices": True,
        "turn_completion_explainer": True,
        "show_cost": False,
        "battery": False,
        "focus_view": False,
        "focus_saved_tool_progress": "all",
        "skin": "default",
        "language": "en",
        "tui_status_indicator": "kaomoji",
        "cli_refresh_interval": 1.0,
        "user_message_preview": {
            "first_lines": 2,
            "last_lines": 2,
        },
        "interim_assistant_messages": True,
        "show_commentary": True,
        "tool_progress_command": False,
        "tool_preview_length": 0,
        "friendly_tool_labels": True,
        "turn_summary": True,
        "spinner_token_flow": True,
        "tool_progress_grouping": "accumulate",
        "status_phrases": {},
        "reasoning_style": "code",
        "ephemeral_system_ttl": 0,
        "platforms": {
            "telegram": {"streaming": True},
            "discord": {"streaming": False},
            "slack": {"streaming": False},
            "wecom": {"streaming": True},
        },
        "runtime_footer": {
            "enabled": False,
            "fields": ["model", "context_pct", "cwd"],
        },
        "status_bar": {
            "fields": [],
        },
        "copy_shortcut": "auto",
        "pet": {
            "enabled": False,
            "slug": "",
            "render_mode": "auto",
            "scale": 0.33,
            "unicode_cols": 0,
        },
    },

    "dashboard": {
        "theme": "default",
        "turn_isolation": False,
        "compute_host_heartbeat_secs": 15,
        "compute_host_respawn_max": 3,
        "show_token_analytics": False,
        "trusted_proxies": [],
        "ws_ping_interval": 20.0,
        "ws_ping_timeout": 20.0,
        "ws_orphan_reap_grace_s": 20.0,
        "ws_orphan_activity_stale_s": 600.0,
        "startup_orphan_sweep": True,
        "oauth": {
            "client_id": "",

        },
        "basic_auth": {
            "username": "",
            "password_hash": "",
            "password": "",
            "secret": "",
            "session_ttl_seconds": 0,
        },
        "drain_auth": {"scope": "drain", "min_secret_chars": 43},
        "public_url": "",
    },

    "privacy": {
        "redact_pii": False,
    },
    "tts": {
        "provider": "edge",
        "edge": {
            "voice": "en-US-AriaNeural",
        },
        "elevenlabs": {
            "voice_id": "pNInz6obpgDQGcFmaJgB",
            "model_id": "eleven_multilingual_v2",
        },
        "openai": {
            "model": "gpt-4o-mini-tts",
            "voice": "alloy",
        },
        "gemini": {
            "model": "gemini-2.5-flash-preview-tts",
            "voice": "Kore",
            "audio_tags": False,
            "persona_prompt_file": "",
        },
        "xai": {
            "voice_id": "eve",
            "language": "en",
            "speed": 1.0,
            "auto_speech_tags": False,
            "optimize_streaming_latency": 0,
            "sample_rate": 24000,
            "bit_rate": 128000,
        },
        "mistral": {
            "model": "voxtral-mini-tts-2603",
            "voice_id": "c69964a6-ab8b-4f8a-9465-ec0925096ec8",
        },
        "minimax": {"model": "speech-02-hd", "voice_id": "English_expressive_narrator"},
        "kittentts": {
            "model": "KittenML/kitten-tts-nano-0.8-int8",
            "voice": "Jasper",
        },
        "neutts": {
            "ref_audio": "",
            "ref_text": "",
            "model": "neuphonic/neutts-air-q4-gguf",
            "device": "cpu",
        },
        "piper": {
            "voice": "en_US-lessac-medium",
        },
        "deepinfra": {
            "model": "",
            "voice": "default",
        },
    },

    "stt": {
        "enabled": True,
        "echo_transcripts": True,
        "language": "en",
        "cloud_trim_silence": True,
        "cloud_trim_threshold_db": -40,
        "cloud_trim_keep_ms": 300,
        "local": {
            "model": "base",
            "language": "",
            "initial_prompt": "",
            "vad": True,
            "vad_min_silence_ms": 500,
            "no_speech_prob_threshold": 0.6,
            "logprob_threshold": -1.0,
            "unload_after_idle_seconds": 0,
        },
        "groq": {
            "model": "whisper-large-v3-turbo",
            "language": "",
        },
        "openai": {
            "model": "whisper-1",
            "language": "",
        },
        "mistral": {
            "model": "voxtral-mini-latest",
            "language": "",
        },
        "xai": {
            "language": "",
        },
        "elevenlabs": {
            "model_id": "scribe_v2",
            "language_code": "",
            "tag_audio_events": False,
            "diarize": False,
        },
        "deepinfra": {
            "model": "",
        },
    },

    "voice": {
        "record_key": "ctrl+b",
        "submit_mode": "direct",
        "max_recording_seconds": 120,
        "auto_tts": False,
        "client_direct": True,
        "beep_enabled": True,
        "beep_volume": 0.3,
        "thinking_sound": True,
        "silence_threshold": 200,
        "silence_duration": 3.0,
        "barge_in": True,
        "barge_in_grace_seconds": 0.5,
        "barge_in_threshold_multiplier": 3.0,
        "stop_phrases": ["stop"],
    },
    "wake_word": {
        "enabled": False,
        "surface": "auto",
        "input_device": None,
        "capture": "auto",
        "provider": "openwakeword",
        "phrase": "hey arkos",
        "sensitivity": 0.6,
        "confirmation_frames": 3,
        "start_new_session": True,
        "profile_routing": True,
        "openwakeword": {
            "model": "hey_arkos",
            "inference_framework": "",
        },
        "sherpa": {
            "model_dir": "",
        },
        "porcupine": {
            "keyword": "jarvis",
        },
    },

    "human_delay": {"mode": "off", "min_ms": 800, "max_ms": 2500},

    "context": {
        "engine": "compressor",
        "memory_trim": {
            "enabled": True,
            "cooldown_seconds": 60.0,
            "log_every_n": 1,
            "info_log_min_delta_mb": 0.0,
        },
    },
    "memory": {
        "memory_enabled": True,
        "user_profile_enabled": True,
        "write_approval": False,
        "memory_char_limit": 2200,
        "user_char_limit": 1375,
        "nudge_interval": 10,
        "provider": "",
    },
    "delegation": {
        "model": "",
        "provider": "",
        "fallback_providers": None,
        "base_url": "",
        "api_key": "",
        "api_mode": "",
        "request_overrides": {},
        "compression_threshold_tokens": 0,
        "inherit_mcp_toolsets": True,
        "max_iterations": 250,
        "max_summary_chars": 24000,
        "child_timeout_seconds": 0,
        "reasoning_effort": "",
        "max_concurrent_children": 10,
        "independent_completions": False,
        "max_spawn_depth": 1,
        "orchestrator_enabled": True,
        "subagent_auto_approve": False,
        "surface_child_process_notifications": False,
    },
    "prefill_messages_file": "",
    "goals": {
        "max_turns": 20,
    },
    "loops": {
        "min_interval_seconds": 30,
        "max_ticks": 100,
        "self_paced_floor_seconds": 60,
        "self_paced_ceiling_seconds": 900,
    },
    "moa": {
        "default_preset": "default",
        "active_preset": "",
        "save_traces": False,
        "trace_dir": "",
        "privacy_filter": "",
        "presets": {
            "default": {
                "reference_models": [
                    {"provider": "openai-codex", "model": "gpt-5.5"},
                    {"provider": "openrouter", "model": "deepseek/deepseek-v4-pro"},
                ],
                "aggregator": {"provider": "openrouter", "model": "anthropic/claude-opus-4.8"},

                "enabled": True,
            }
        },
    },
    "skills": {
        "external_dirs": [],
        "create_dir": "",
        "project_discovery": True,
        "trusted_project_dirs": [],
        "template_vars": True,
        "inline_shell": False,
        "inline_shell_timeout": 10,
        "guard_agent_created": False,
        "tier1_advisory": True,
        "write_approval": False,
        "ledger": True,
    },
    "curator": {
        "enabled": True,
        "interval_hours": 24 * 7,
        "min_idle_hours": 2,
        "stale_after_days": 30,
        "archive_after_days": 90,
        "consolidate": False,
        "prune_builtins": True,
        "archive_ttl_days": 0,
        "backup": {
            "enabled": True,
            "keep": 5,
        },
    },
    "honcho": {},
    "timezone": "",

    "slack": {
        "require_mention": True,
        "free_response_channels": "",
        "allowed_channels": "",
        "require_mention_channels": "",
        "ignore_other_user_mentions": False,
        "thread_require_mention": False,
        "channel_prompts": {},
    },

    "discord": {
        "require_mention": True,
        "free_response_channels": "",
        "allowed_channels": "",
        "auto_thread": True,
        "thread_require_mention": False,
        "bots_require_inline_mention": False,
        "history_backfill": True,
        "history_backfill_limit": 50,
        "missed_message_backfill": {
            "enabled": False,
            "channels": "",
            "window_seconds": 21600,
            "limit": 100,
            "max_dispatches": 10,
        },
        "reactions": True,
        "websocket_liveness_interval_seconds": 15,
        "websocket_liveness_failure_threshold": 2,
        "websocket_heartbeat_ack_max_age_seconds": 60,
        "websocket_max_latency_seconds": 30,
        "channel_prompts": {},
        "dm_role_auth_guild": "",
        "server_actions": "",
        "allow_any_attachment": False,
        "max_attachment_bytes": 33554432,
        "approval_mentions": False,
        "voice_channel_inactivity_timeout_seconds": 300,
        "voice_playback_timeout_seconds": 120,
        "voice_fx": {
            "enabled": False,
            "ambient_enabled": True,
            "ambient_path": "",
            "ambient_gain": 0.18,
            "duck_gain": 0.06,
            "speech_gain": 1.0,
            "ack_enabled": True,
            "ack_phrases": [
                "Let me look into that.",
                "One moment.",
                "Checking on that now.",
                "Give me a sec.",
                "On it.",
            ],
        },
    },

    "whatsapp": {
    },

    "telegram": {
        "reactions": False,
        "channel_prompts": {},
        "allowed_chats": "",
        "extra": {
            "rich_messages": False,
            "rich_drafts": False,
        },
    },

    "mattermost": {
        "require_mention": True,
        "free_response_channels": "",
        "allowed_channels": "",
        "channel_prompts": {},
    },

    "matrix": {
        "require_mention": True,
        "free_response_rooms": "",
        "allowed_rooms": "",
    },
    "approvals": {
        "mode": "smart",
        "timeout": 300,
        "cron_mode": "deny",
        "single_query_mode": "deny",
        "unattended_mode": "deny",
        "smart_policy": "",
        "denial_breaker_threshold": 3,
        "deny": [],
        "mcp_reload_confirm": True,
        "destructive_slash_confirm": True,
    },
    "command_allowlist": [],
    "quick_commands": {},
    "platform_hints": {},
    "plugins": {
        "hook_callback_timeout": 30,
    },
    "hooks": {},
    "hooks_auto_accept": False,
    "personalities": {},
    "security": {
        "allow_private_urls": False,
        "redact_secrets": True,
        "allow_data_training_tiers_noninteractive": False,
        "approval": {"transport": "builtin", "transport_fallback": "deny"},
        "protected_instruction_files": True,
        "protected_instruction_extra_patterns": [],
        "tirith_enabled": True,
        "tirith_path": "tirith",
        "tirith_timeout": 5,
        "tirith_fail_open": True,
        "website_blocklist": {"enabled": False, "domains": [], "shared_files": []},
        "acked_advisories": [],
        "allow_lazy_installs": True,
    },

    "cron": {
        "allow_agent_scheduling": False,
        "preflight": True,
        "model_drift_guard": True,
        "model": "",
        "model_provider": "",
        "provider": "",
        "wrap_response": True,
        "delivery": {
            "notify": True,
        },
        "mirror_delivery": False,
        "max_parallel_jobs": None,
        "output_retention": 50,
        "script_timeout_seconds": 3600,
        "session_db_timeout_seconds": 10,
        "media_send_timeout_seconds": 300,
    },
    "kanban": {
        "auto_subscribe_on_create": True,
        "dispatch_in_gateway": True,
        "review_dispatch": True,
        "dispatch_interval_seconds": 60,
        "failure_limit": 2,
        "worker_log_rotate_bytes": 2 * 1024 * 1024,
        "worker_log_backup_count": 1,
        "orchestrator_profile": "",
        "default_assignee": "",
        "max_in_progress": None,
        "max_in_progress_per_profile": None,
        "auto_decompose": True,
        "auto_decompose_per_tick": 3,
        "dispatch_stale_timeout_seconds": 14400,
        "reconcile_orphans": True,
        "done_sub_retention_days": 30,
    },
    "bot_mode": {
        "envelope_ttl_seconds": 900,
        "turn_wait_seconds": 120,
    },
    "code_execution": {
        "mode": "project",
        "kernel_idle_timeout": 1800,
        "max_session_kernels": 4,
    },
    "tools": {
        "tool_search": {
            "enabled": "auto",
            "threshold_pct": 5,
            "search_default_limit": 5,
            "max_search_limit": 25,
            "listing": "auto",
            "listing_max_tokens": 4000,
        },
    },
    "logging": {
        "level": "INFO",
        "max_size_mb": 5,
        "backup_count": 3,
    },
    "model_catalog": {
        "enabled": False,
        "url": "",
        "ttl_minutes": 20,
        "providers": {},
    },
    "model_overrides": {},
    "models_dev": {
        "url": "",
    },

    "network": {
        "force_ipv4": False,
    },
    "monitoring": {
        "install_id": "",
        "gateway_health_export": {
            "enabled": False,
            "metrics_enabled": True,
            "diagnostic_events_enabled": True,
            "warning_error_events_enabled": True,
            "export_interval_seconds": 60,
            "logs_export_interval_seconds": 5,
            "resource_attributes": {
                "service.name": "arkos-gateway", "deployment.environment.name": "production"
            },
        },
        "export": {"otlp": {"enabled": False, "endpoint": "", "headers_env": {}}},
    },
    "gateway": {
        "multiplex_profile_allowlist": None,
        "signal_interrupt_grace_timeout": 1,
        "delivery_ledger": True,
        "platform_connect_timeout": 30,
        "loop_watchdog": True,
        "loop_watchdog_probe_interval_s": 30.0,
        "loop_watchdog_probe_timeout_s": 10.0,
        "loop_watchdog_max_strikes": 3,
        "startup_watchdog": True,
        "startup_watchdog_timeout_seconds": 300,
        "write_sessions_json": True,
        "scale_to_zero": {"idle_timeout_minutes": 2},
        "restart_loop_guard": {"max_restarts": 3, "window_seconds": 60, "max_gap_seconds": 300},
        "respawn_storm": {"max_starts": 5, "window_seconds": 120},
        "message_timestamps": {"enabled": False},
        "max_inbound_media_bytes": 134217728,
        "trust_env": True,
        "strict": False,
        "media_delivery_allow_dirs": [],
        "trust_recent_files": True,
        "trust_recent_files_seconds": 600,
        "api_server": {
            "max_concurrent_runs": 10,
        },
    },
    "streaming": {
        "enabled": False,
        "transport": "auto",
        "edit_interval": 0.8,
        "buffer_threshold": 24,
        "cursor": " \u2589",
        "fresh_final_after_seconds": 0.0,
    },
    "sessions": {
        "auto_prune": True,
        "retention_days": 90,
        "auto_archive": False,
        "auto_archive_days": 3,
        "vacuum_after_prune": True,
        "min_vacuum_interval_days": 30,
        "min_interval_hours": 24,

        "fts_optimize_notice": "advise",
        "cjk_fts": True,
        "search_slow_ms": 1000,
        "max_resume_messages": 20000,
        "max_export_messages": 20000,
    },
    "onboarding": {
        "seen": {},
        "profile_build": "ask",
    },
    "telemetry": {
        "shared_metrics": {
            "enabled": False,
            "send": False,
            "endpoint": "",
        },
    },

    "doctor": {
        "live_probe_timeout": 10,
    },

    "updates": {
        "check": True,
        "pre_update_backup": "quick",
        "backup_keep": 5,
        "non_interactive_local_changes": "stash",
        "auto_switch_parked_branch": True,
        "parked_branch_strategy": "switch",
        "refresh_cua_driver": True,
    },
    "lsp": {
        "enabled": True,
        "wait_mode": "document",
        "wait_timeout": 5.0,
        "install_strategy": "auto",
        "idle_timeout": 600.0,
        "servers": {},
    },
    "x_search": {
        "model": "grok-4.5",
        "reasoning_effort": None,
        "timeout_seconds": 180,
        "retries": 2,
    },
    "secrets": {
        "bitwarden": {
            "enabled": False,
            "access_token_env": "BWS_ACCESS_TOKEN",
            "project_id": "",
            "cache_ttl_seconds": 300,
            "encrypted_cache": {"enabled": False, "max_stale_seconds": 0},
            "override_existing": True,
            "auto_install": True,
            "server_url": "",
        },
        "onepassword": {
            "enabled": False,
            "env": {},
            "account": "",
            "service_account_token_env": "OP_SERVICE_ACCOUNT_TOKEN",
            "binary_path": "",
            "cache_ttl_seconds": 300,
            "override_existing": True,
        },
    },
    "paste_collapse_threshold": 5,
    "paste_collapse_threshold_fallback": 5,
    "paste_collapse_char_threshold": 2000,

    "computer_use": {
        "cua_telemetry": False,
        "native_wayland": False,
        "max_image_dimension": 1456,
        "capture_after_mode": "som",
        "no_overlay": None,
        "permission_mode": "standard",
        "capability_manifest": "",
        "allow_unsigned_driver": False,
    },
    "proxy": {
        "enabled": False,
        "tunnel_port": 9090,
        "auto_install": True,
        "credential_source": "env",
        "enforce_on_docker": True,
        "allow_env_fallback": False,
        "upstream_deny_cidrs": None,
        "extra_allowed_hosts": [],
    },
    "desktop": {
        "repo_scan_enabled": True,
        "repo_scan_roots": [],
        "repo_scan_exclude_paths": [],
        "electron_flags": [],
        "ozone_platform_hint": "auto",
        "disable_gpu": "auto",
        "password_store": "auto",
        "manage_launcher_entry": True,
        "macos_signing_identity": "",
        "auto_continue": {
            "enabled": True,
            "freshness_minutes": 15,
            "max_attempts": 2,
        },
    },


    "vertex": {
        "project_id": "",
        "region": "global",
    },
    "local_runtime": {
        "enabled": False,
        "tag": "b10679",
        "backend": "auto",
        "models_max": 4,
        "port": 0,
        "detect_ports": [],
    },
    "_config_version": 41,
}


def _env(description, prompt, **keys):
    """One OPTIONAL_ENV_VARS entry; keyword order is preserved as dict key order."""
    return {"description": description, "prompt": prompt, **keys}


_OMIT = object()


def _category(category, password, advanced):
    """Entry factory for one category with its usual password/advanced defaults.

    ``url``/``help``/``tools`` are only written when passed; ``password=None`` omits the key;
    ``advanced`` is only written when true. Key order matches the plain ``_env`` entries.
    """
    def make(description, prompt, url=_OMIT, *, help=_OMIT, tools=_OMIT, password=password,
             advanced=advanced):
        d = {"description": description, "prompt": prompt}
        d.update((k, v) for k, v in (("help", help), ("url", url), ("tools", tools)) if v is not _OMIT)
        if password is not None:
            d["password"] = password
        d["category"] = category
        if advanced:
            d["advanced"] = True
        return d
    return make


_prov = _category("provider", password=True, advanced=True)
_tool = _category("tool", password=True, advanced=False)
_msg = _category("messaging", password=False, advanced=False)
_skill = _category("skill", password=True, advanced=True)
_setting = _category("setting", password=False, advanced=False)


def _base_url(name, prompt_name=None):
    """Provider ``*_BASE_URL`` override entry (advanced, not a secret)."""
    prompt = f"{prompt_name or name} base URL (leave empty for default)"
    return _prov(f"{name} base URL override", prompt, None, password=False)


OPTIONAL_ENV_VARS = {

    "OPENROUTER_API_KEY": _env("OpenRouter API key (for vision, web scraping helpers, and MoA)",
        "OpenRouter API key", url="https://openrouter.ai/keys", password=True, tools=["vision_analyze"],
        category="provider", advanced=True),
    "GOOGLE_API_KEY": _prov("Google AI Studio API key (also recognized as GEMINI_API_KEY)",
        "Google AI Studio API key", "https://aistudio.google.com/app/apikey"),
    "GEMINI_API_KEY": _prov("Google AI Studio API key (alias for GOOGLE_API_KEY)", "Gemini API key",
        "https://aistudio.google.com/app/apikey"),
    "GEMINI_BASE_URL": _base_url("Google AI Studio", "Gemini"),
    "VERTEX_CREDENTIALS_PATH": _prov(
        "Path to a Google Cloud service account JSON for Vertex AI (Gemini). Vertex uses "
        "OAuth2, not a static API key — this points at the credentials Arkos mints short-lived "
        "tokens from. Falls back to GOOGLE_APPLICATION_CREDENTIALS, then to ADC (gcloud auth "
        "application-default login). Set project/region under vertex: in config.yaml.",
        "Vertex service account JSON path (leave empty to use ADC / "
        "GOOGLE_APPLICATION_CREDENTIALS)", "https://cloud.google.com/iam/docs/keys-create-delete",
        password=False),
    "XAI_API_KEY": _prov("xAI API key", "xAI API key", "https://console.x.ai/"),
    "XAI_BASE_URL": _base_url("xAI"),
    "NVIDIA_API_KEY": _prov("NVIDIA NIM API key (build.nvidia.com or local NIM endpoint)",
        "NVIDIA NIM API key", "https://build.nvidia.com/"),
    "NVIDIA_BASE_URL": _prov(
        "NVIDIA NIM base URL override (e.g. http://localhost:8000/v1 for local NIM)",
        "NVIDIA NIM base URL (leave empty for default)", None, password=False),
    "LM_API_KEY": _prov("LM Studio bearer token for auth-enabled local servers",
        "LM Studio API key / bearer token", None),
    "LM_BASE_URL": _base_url("LM Studio"),
    "GLM_API_KEY": _prov("Z.AI / GLM API key (also recognized as ZAI_API_KEY / Z_AI_API_KEY)",
        "Z.AI / GLM API key", "https://z.ai/"),
    "ZAI_API_KEY": _prov("Z.AI API key (alias for GLM_API_KEY)", "Z.AI API key", "https://z.ai/"),
    "Z_AI_API_KEY": _prov("Z.AI API key (alias for GLM_API_KEY)", "Z.AI API key", "https://z.ai/"),
    "GLM_BASE_URL": _base_url("Z.AI / GLM"),
    "KIMI_API_KEY": _prov("Kimi / Moonshot API key", "Kimi API key",
        "https://platform.moonshot.cn/"),
    "KIMI_BASE_URL": _base_url("Kimi / Moonshot", "Kimi"),
    "KIMI_CN_API_KEY": _prov("Kimi / Moonshot China API key", "Kimi (China) API key",
        "https://platform.moonshot.cn/"),
    "STEPFUN_API_KEY": _prov("StepFun Step Plan API key", "StepFun Step Plan API key",
        "https://platform.stepfun.com/"),
    "STEPFUN_BASE_URL": _base_url("StepFun Step Plan"),
    "ARCEEAI_API_KEY": _prov("Arcee AI API key", "Arcee AI API key", "https://chat.arcee.ai/"),
    "ARCEE_BASE_URL": _base_url("Arcee AI", "Arcee"),
    "GMI_API_KEY": _prov("GMI Cloud API key", "GMI Cloud API key", "https://www.gmicloud.ai/"),
    "GMI_BASE_URL": _base_url("GMI Cloud"),
    "ACTUAL_API_KEY": _prov("Actual Computer inference key (ac_...)",
        "Actual Computer inference key", "https://actual.inc/user/keys"),
    "ACTUAL_BASE_URL": _prov(
        "Actual Computer base URL override (set to http://127.0.0.1:8080 for the local offline "
        "daemon)", "Actual Computer base URL (leave empty for hosted relay)", None, password=False),
    "FIREWORKS_API_KEY": _prov("Fireworks AI API key", "Fireworks AI API key",
        "https://app.fireworks.ai/settings/users/api-keys"),
    "MINIMAX_API_KEY": _prov("MiniMax API key (international)", "MiniMax API key",
        "https://www.minimax.io/"),
    "MINIMAX_BASE_URL": _base_url("MiniMax"),
    "MINIMAX_CN_API_KEY": _prov("MiniMax API key (China endpoint)", "MiniMax (China) API key",
        "https://www.minimaxi.com/"),
    "MINIMAX_CN_BASE_URL": _base_url("MiniMax (China)"),
    "DEEPSEEK_API_KEY": _prov("DeepSeek API key for direct DeepSeek access", "DeepSeek API Key",
        "https://platform.deepseek.com/api_keys", advanced=False),
    "DEEPSEEK_BASE_URL": _prov("Custom DeepSeek API base URL (advanced)", "DeepSeek Base URL", "",
        password=False, advanced=False),
    "DASHSCOPE_API_KEY": _prov("Alibaba Cloud DashScope API key (Qwen + multi-provider models)",
        "DashScope API Key", "https://modelstudio.console.alibabacloud.com/", advanced=False),
    "DASHSCOPE_BASE_URL": _prov(
        "Custom DashScope base URL (default: coding-intl OpenAI-compat endpoint)",
        "DashScope Base URL", "", password=False),
    "ARKOS_QWEN_BASE_URL": _prov(
        "Qwen Portal base URL override (default: https://portal.qwen.ai/v1)",
        "Qwen Portal base URL (leave empty for default)", None, password=False),
    "OPENCODE_ZEN_API_KEY": _prov("OpenCode Zen API key (pay-as-you-go access to curated models)",
        "OpenCode Zen API key", "https://opencode.ai/auth"),
    "COMMANDCODE_API_KEY": _prov(
        "CommandCode API key (GOAT/Pro/Max/Provider plans — 30+ models via one key)",
        "CommandCode API key", "https://commandcode.ai/studio/"),
    "OPENCODE_ZEN_BASE_URL": _base_url("OpenCode Zen"),
    "OPENCODE_GO_API_KEY": _prov("OpenCode Go API key ($10/month subscription for open models)",
        "OpenCode Go API key", "https://opencode.ai/auth"),
    "OPENCODE_GO_BASE_URL": _base_url("OpenCode Go"),
    "HF_TOKEN": _prov(
        "Hugging Face token for Inference Providers (20+ open models via router.huggingface.co)",
        "Hugging Face Token", "https://huggingface.co/settings/tokens", advanced=False),
    "HF_BASE_URL": _base_url("Hugging Face Inference Providers", "HF"),
    "OLLAMA_API_KEY": _prov("Ollama Cloud API key (ollama.com — cloud-hosted open models)",
        "Ollama Cloud API key", "https://ollama.com/settings"),
    "OLLAMA_BASE_URL": _prov("Ollama Cloud base URL override (default: https://ollama.com/v1)",
        "Ollama base URL (leave empty for default)", None, password=False),
    "XIAOMI_API_KEY": _prov(
        "Xiaomi MiMo API key for MiMo models (mimo-v2.5-pro, mimo-v2.5, mimo-v2-pro, "
        "mimo-v2-omni, mimo-v2-flash)", "Xiaomi MiMo API Key", "https://platform.xiaomimimo.com",
        advanced=False),
    "XIAOMI_BASE_URL": _prov(
        "Xiaomi MiMo base URL override (default: https://api.xiaomimimo.com/v1)",
        "Xiaomi base URL (leave empty for default)", None, password=False),
    "UPSTAGE_API_KEY": _prov("Upstage API key for Solar LLM models", "Upstage API Key",
        "https://console.upstage.ai/api-keys", advanced=False),
    "UPSTAGE_BASE_URL": _prov("Upstage base URL override (default: https://api.upstage.ai/v1)",
        "Upstage base URL (leave empty for default)", None, password=False),
    "AWS_REGION": _prov("AWS region for Bedrock API calls (e.g. us-east-1, eu-central-1)",
        "AWS Region", "https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-regions.html",
        password=False),
    "AWS_PROFILE": _prov("AWS named profile for Bedrock authentication (from ~/.aws/credentials)",
        "AWS Profile", None, password=False),
    "AZURE_FOUNDRY_API_KEY": _prov("Azure Foundry API key for custom Azure endpoints",
        "Azure Foundry API Key", "https://ai.azure.com/", advanced=False),
    "AZURE_FOUNDRY_BASE_URL": _prov(
        "Azure Foundry base URL (set via 'arkos model' for endpoint-specific config)",
        "Azure Foundry base URL", None, password=False),
    "EXA_API_KEY": _tool("Exa API key for AI-native web search and contents", "Exa API key",
        "https://exa.ai/", tools=["web_search", "web_extract"]),
    "PARALLEL_API_KEY": _tool("Parallel API key for AI-native web search and extract",
        "Parallel API key", "https://parallel.ai/", tools=["web_search", "web_extract"]),
    "FIRECRAWL_API_KEY": _tool("Firecrawl API key for web search and scraping", "Firecrawl API key",
        "https://firecrawl.dev/", tools=["web_search", "web_extract"]),
    "FIRECRAWL_API_URL": _tool("Firecrawl API URL for self-hosted instances (optional)",
        "Firecrawl API URL (leave empty for cloud)", None, password=False, advanced=True),


    "TAVILY_API_KEY": _tool(
        "Tavily API key for AI-native web search and extract (optional — keyless works when "
        "Tavily is selected)", "Tavily API key", "https://app.tavily.com/home",
        tools=["web_search", "web_extract"]),
    "PERPLEXITY_API_KEY": _tool(
        "Perplexity API key for the Search API web backend (ranked results + query-relevant page "
        "snippets)", "Perplexity API key", "https://www.perplexity.ai/account/api",
        tools=["web_search", "web_extract"]),
    "KEENABLE_API_KEY": _tool(
        "Keenable API key for fast independent-index web search and page fetch (optional — "
        "keyless free tier works without it)", "Keenable API key", "https://keenable.ai",
        tools=["web_search", "web_extract"]),
    "SEARXNG_URL": _tool("URL of your SearXNG instance for free self-hosted web search",
        "SearXNG URL (e.g. http://localhost:8080)", "https://searxng.github.io/searxng/",
        tools=["web_search"], password=False),
    "BRAVE_SEARCH_API_KEY": _tool(
        "Brave Search API subscription token (free tier: 2,000 queries/mo)",
        "Brave Search subscription token", "https://brave.com/search/api/", tools=["web_search"]),
    "BROWSERBASE_API_KEY": _tool(
        "Browserbase API key for cloud browser (optional — local browser works without this)",
        "Browserbase API key", "https://browserbase.com/",
        tools=["browser_navigate", "browser_click"]),
    "BROWSERBASE_PROJECT_ID": _tool(
        "Browserbase project ID (optional — only needed for cloud browser)",
        "Browserbase project ID", "https://browserbase.com/",
        tools=["browser_navigate", "browser_click"], password=False),
    "BROWSER_USE_API_KEY": _tool(
        "Browser Use API key for cloud browser (optional — local browser works without this)",
        "Browser Use API key", "https://browser-use.com/",
        tools=["browser_navigate", "browser_click"]),
    "FIRECRAWL_BROWSER_TTL": _tool(
        "Firecrawl browser session TTL in seconds (optional, default 300)",
        "Browser session TTL (seconds)", tools=["browser_navigate", "browser_click"],
        password=False),
    "AGENT_BROWSER_ENGINE": _env(
        "Local browser engine: auto (default Chrome), lightpanda (faster, no screenshots; Browser Use mode "
        "spawns lightpanda serve), chrome", "Browser engine (auto/lightpanda/chrome)",
        url="https://lightpanda.io/docs/run-locally/installation/one-liner",
        tools=["browser_exec", "browser_navigate", "browser_snapshot", "browser_click", "browser_vision"],
        password=False, category="tool", advanced=True),
    "CAMOFOX_URL": _tool(
        "Camofox browser server URL for local anti-detection browsing (e.g. http://localhost:9377)",
        "Camofox server URL", "https://github.com/jo-inc/camofox-browser",
        tools=["browser_navigate", "browser_click"], password=False),
    "CAMOFOX_API_KEY": _tool(
        "Optional bearer token sent as Authorization header to a remote/authenticated Camofox "
        "server", "Camofox API key", "https://github.com/jo-inc/camofox-browser",
        tools=["browser_navigate", "browser_click"], advanced=True),
    "FAL_KEY": _tool("FAL API key for image and video generation", "FAL API key", "https://fal.ai/",
        tools=["image_generate", "video_generate"]),
    "KREA_API_KEY": _tool("Krea API key for Krea 2 image generation (Medium + Large)",
        "Krea API key", "https://www.krea.ai/settings/api-tokens", tools=["image_generate"]),
    "VOICE_TOOLS_OPENAI_KEY": _tool(
        "OpenAI API key for voice transcription (Whisper) and OpenAI TTS",
        "OpenAI API Key (for Whisper STT + TTS)", "https://platform.openai.com/api-keys",
        tools=["voice_transcription", "openai_tts"]),
    "ELEVENLABS_API_KEY": _tool(
        "ElevenLabs API key for premium text-to-speech voices and Scribe transcription",
        "ElevenLabs API key", "https://elevenlabs.io/",
        tools=["elevenlabs_tts", "voice_transcription"]),
    "MISTRAL_API_KEY": _tool("Mistral API key for Voxtral TTS and transcription (STT)",
        "Mistral API key", "https://console.mistral.ai/"),
    "PORCUPINE_ACCESS_KEY": _tool(
        "Picovoice access key for the Porcupine 'Hey Arkos' wake word engine (optional; "
        "openWakeWord is the free default)", "Picovoice access key",
        "https://console.picovoice.ai/"),
    "GITHUB_TOKEN": _tool("GitHub token for Skills Hub (higher API rate limits, skill publish)",
        "GitHub Token", "https://github.com/settings/tokens"),
    "NOTION_API_KEY": _skill("Notion integration token (used by the `notion` skill)",
        "Notion API key", "https://www.notion.so/my-integrations"),
    "LINEAR_API_KEY": _skill("Linear personal API key (used by the `linear` skill)",
        "Linear API key", "https://linear.app/settings/account/security"),
    "AIRTABLE_API_KEY": _skill("Airtable personal access token (used by the `airtable` skill)",
        "Airtable API key", "https://airtable.com/create/tokens"),
    "TENOR_API_KEY": _skill("Tenor API key for GIF search (used by the `gif-search` skill)",
        "Tenor API key", "https://developers.google.com/tenor/guides/quickstart"),
    "HONCHO_API_KEY": _tool("Honcho API key for AI-native persistent memory", "Honcho API key",
        "https://app.honcho.dev", tools=["honcho_context"]),
    "HONCHO_BASE_URL": _tool("Base URL for self-hosted Honcho instances (no API key needed)",
        "Honcho base URL (e.g. http://localhost:8000)", password=None),
    "HINDSIGHT_API_KEY": _tool("Hindsight API key for graph-aware persistent memory",
        "Hindsight API key", "https://hindsight.vectorize.io", tools=["hindsight_recall"]),
    "HINDSIGHT_API_URL": _tool(
        "Base URL for the Hindsight API (default: https://api.hindsight.vectorize.io)",
        "Hindsight API URL", password=None, advanced=True),
    "SUPERMEMORY_API_KEY": _tool("Supermemory API key for conversation-scoped persistent memory",
        "Supermemory API key", "https://supermemory.ai", tools=["supermemory_search"]),
    "MEM0_API_KEY": _tool("Mem0 Platform API key for semantic persistent memory", "Mem0 API key",
        "https://app.mem0.ai", tools=["mem0_search"]),
    "RETAINDB_API_KEY": _tool("RetainDB API key for persistent memory", "RetainDB API key",
        "https://retaindb.com", tools=["retaindb_search"]),
    "RETAINDB_BASE_URL": _tool(
        "Base URL for self-hosted RetainDB instances (default: https://api.retaindb.com)",
        "RetainDB base URL", password=None, advanced=True),
    "BRV_API_KEY": _tool("ByteRover API key (optional, for cloud sync — local-first by default)",
        "ByteRover API key", "https://app.byterover.dev", tools=["brv_query"]),
    "OPENVIKING_API_KEY": _tool("OpenViking API key (leave blank for local dev mode)",
        "OpenViking API key", tools=["viking_search"]),
    "OPENVIKING_ENDPOINT": _tool("OpenViking server URL (default: http://127.0.0.1:1933)",
        "OpenViking endpoint", password=None, advanced=True),
    "ARKOS_LANGFUSE_PUBLIC_KEY": _tool("Langfuse project public key (pk-lf-...)",
        "Langfuse public key", "https://cloud.langfuse.com", password=False),
    "ARKOS_LANGFUSE_SECRET_KEY": _tool("Langfuse project secret key (sk-lf-...)",
        "Langfuse secret key", "https://cloud.langfuse.com"),
    "ARKOS_LANGFUSE_BASE_URL": _tool("Langfuse server URL (default: https://cloud.langfuse.com)",
        "Langfuse server URL (leave empty for cloud.langfuse.com)", None, password=False,
        advanced=True),
    "TELEGRAM_BOT_TOKEN": _msg(
        "Complete Telegram bot token created by @BotFather (numeric bot ID followed by a colon "
        "and secret)", "Telegram bot token", "https://t.me/BotFather", password=True),
    "TELEGRAM_ALLOWED_USERS": _msg(
        "Optional comma-separated numeric Telegram user IDs allowed immediately; leave blank to "
        "approve new users through DM pairing", "Allowed Telegram user IDs (comma-separated)",
        "https://t.me/userinfobot"),
    "TELEGRAM_PROXY": _msg(
        "Proxy URL for Telegram connections (overrides HTTPS_PROXY). Supports http://, "
        "https://, socks5://", "Telegram proxy URL (optional)"),
    "DISCORD_BOT_TOKEN": _msg("Discord bot token from Developer Portal", "Discord bot token",
        "https://discord.com/developers/applications", password=True),
    "DISCORD_ALLOWED_USERS": _msg("Comma-separated Discord user IDs allowed to use the bot",
        "Allowed Discord user IDs (comma-separated)", None),
    "DISCORD_REPLY_TO_MODE": _msg(
        "Discord reply threading mode: 'off' (no reply references), 'first' (reply on first "
        "message only, default), 'all' (reply on every chunk)",
        "Discord reply mode (off/first/all)", None),
    "SLACK_BOT_TOKEN": _msg(
        "Slack bot token (xoxb-). Get from OAuth & Permissions after installing your app. "
        "Required scopes: chat:write, app_mentions:read, channels:history, groups:history, "
        "im:history, im:read, im:write, mpim:history, mpim:read, users:read, files:read, "
        "files:write", "Slack Bot Token (xoxb-...)", "https://api.slack.com/apps",
        help=("In your Slack app, add the required bot scopes, install the app to the workspace, "
        "then copy OAuth & Permissions > Bot User OAuth Token."), password=True),
    "SLACK_APP_TOKEN": _msg(
        "Slack app-level token (xapp-) for Socket Mode. Get from Basic Information → App-Level "
        "Tokens. Also ensure Event Subscriptions include: message.im, message.channels, "
        "message.groups, message.mpim, app_mention", "Slack App Token (xapp-...)",
        "https://api.slack.com/apps",
        help=("In your Slack app, enable Socket Mode, then create Basic Information > App-Level "
        "Tokens with the connections:write scope."), password=True),
    "SLACK_ALLOWED_USERS": _msg(
        "Comma-separated Slack member IDs allowed to use Arkos, e.g. U01ABC2DEF3. Without "
        "this, Slack may connect but deny messages by default.", "Allowed Slack member IDs",
        "https://api.slack.com/apps",
        help=("In Slack, open your profile, choose More or the three-dot menu, then Copy member "
        "ID. Add multiple IDs comma-separated.")),
    "MATTERMOST_URL": _msg("Mattermost server URL (e.g. https://mm.example.com)",
        "Mattermost server URL", "https://mattermost.com/deploy/"),
    "MATTERMOST_TOKEN": _msg("Mattermost bot token or personal access token",
        "Mattermost bot token", None, password=True),
    "MATTERMOST_ALLOWED_USERS": _msg("Comma-separated Mattermost user IDs allowed to use the bot",
        "Allowed Mattermost user IDs (comma-separated)", None),
    "MATTERMOST_REQUIRE_MENTION": _msg(
        "Require @mention in Mattermost channels (default: true). Set to false to respond to "
        "all messages.", "Require @mention in channels", None),
    "MATTERMOST_FREE_RESPONSE_CHANNELS": _msg(
        "Comma-separated Mattermost channel IDs where bot responds without @mention",
        "Free-response channel IDs (comma-separated)", None),
    "MATRIX_HOMESERVER": _msg("Matrix homeserver URL (e.g. https://matrix.example.org)",
        "Matrix homeserver URL", "https://matrix.org/ecosystem/servers/"),
    "MATRIX_ACCESS_TOKEN": _msg("Matrix access token (preferred over password login)",
        "Matrix access token", None, password=True),
    "MATRIX_USER_ID": _msg("Matrix user ID (e.g. @arkos:example.org)",
        "Matrix user ID (@user:server)", None),
    "MATRIX_ALLOWED_USERS": _msg(
        "Comma-separated Matrix user IDs allowed to use the bot (@user:server format)",
        "Allowed Matrix user IDs (comma-separated)", None),
    "MATRIX_REQUIRE_MENTION": _msg(
        "Require @mention in Matrix rooms (default: true). Set to false to respond to all "
        "messages.", "Require @mention in rooms (true/false)", None, advanced=True),
    "MATRIX_FREE_RESPONSE_ROOMS": _msg(
        "Comma-separated Matrix room IDs where bot responds without @mention",
        "Free-response room IDs (comma-separated)", None, advanced=True),
    "MATRIX_AUTO_THREAD": _msg("Auto-create threads for messages in Matrix rooms (default: true)",
        "Auto-create threads in rooms (true/false)", None, advanced=True),
    "MATRIX_DM_AUTO_THREAD": _msg("Auto-create threads for DM messages in Matrix (default: false)",
        "Auto-create threads in DMs (true/false)", None, advanced=True),
    "MATRIX_DEVICE_ID": _msg(
        "Stable Matrix device ID for E2EE persistence across restarts (e.g. ARKOS_BOT)",
        "Matrix device ID (stable across restarts)", None, advanced=True),
    "MATRIX_RECOVERY_KEY": _msg(
        "Matrix recovery key for cross-signing verification after device key rotation (from "
        "Element: Settings → Security → Recovery Key)", "Matrix recovery key", None, password=True,
        advanced=True),
    "BLUEBUBBLES_SERVER_URL": _msg(
        "BlueBubbles server URL for iMessage integration (e.g. http://192.168.1.10:1234)",
        "BlueBubbles server URL", "https://bluebubbles.app/"),
    "BLUEBUBBLES_PASSWORD": _msg(
        "BlueBubbles server password (from BlueBubbles Server → Settings → API)",
        "BlueBubbles server password", None, password=True),
    "BLUEBUBBLES_ALLOWED_USERS": _msg(
        "Comma-separated iMessage addresses (email or phone) allowed to use the bot",
        "Allowed iMessage addresses (comma-separated)", None),
    "BLUEBUBBLES_ALLOW_ALL_USERS": _msg("Allow all BlueBubbles users without allowlist",
        "Allow All BlueBubbles Users", password=None),
    "QQ_APP_ID": _msg("QQ Bot App ID from QQ Open Platform (q.qq.com)", "QQ App ID",
        "https://q.qq.com", password=None),
    "QQ_CLIENT_SECRET": _msg("QQ Bot Client Secret from QQ Open Platform", "QQ Client Secret",
        password=True),
    "QQ_ALLOWED_USERS": _msg("Comma-separated QQ user IDs allowed to use the bot",
        "QQ Allowed Users", password=None),
    "QQ_GROUP_ALLOWED_USERS": _msg("Comma-separated QQ group IDs allowed to interact with the bot",
        "QQ Group Allowed Users", password=None),
    "QQ_ALLOW_ALL_USERS": _msg("Allow all QQ users without an allowlist (true/false)",
        "Allow All QQ Users", password=None),
    "QQBOT_HOME_CHANNEL": _msg("Default QQ channel/group for cron delivery and notifications",
        "QQ Home Channel", password=None),
    "QQBOT_HOME_CHANNEL_NAME": _msg("Display name for the QQ home channel", "QQ Home Channel Name",
        password=None),
    "QQ_SANDBOX": _msg("Enable QQ sandbox mode for development testing (true/false)",
        "QQ Sandbox Mode", password=None),
    "IRC_SERVER": _msg("IRC server hostname (e.g. irc.libera.chat)", "IRC server", None),
    "IRC_CHANNEL": _msg("IRC channel to join (e.g. #arkos)", "IRC channel", None),
    "IRC_NICKNAME": _msg("Bot nickname on IRC (default: arkos-bot)", "IRC nickname", None),
    "IRC_SERVER_PASSWORD": _msg("IRC server password (if required)", "IRC server password", None,
        password=True, advanced=True),
    "IRC_NICKSERV_PASSWORD": _msg("NickServ password for nick identification", "NickServ password",
        None, password=True, advanced=True),
    "GATEWAY_ALLOW_ALL_USERS": _msg(
        "Allow all users to interact with messaging bots (true/false). Default: false.",
        "Allow all users (true/false)", None, advanced=True),
    "API_SERVER_ENABLED": _msg(
        "Enable the OpenAI-compatible API server (true/false). Allows frontends like Open "
        "WebUI, LobeChat, etc. to connect.", "Enable API server (true/false)", None, advanced=True),
    "API_SERVER_KEY": _msg(
        "Bearer token for API server authentication. Required whenever the API server is "
        "enabled; server refuses to start without it.", "API server auth key", None, password=True,
        advanced=True),
    "API_SERVER_PORT": _msg("Port for the API server (default: 8642).", "API server port", None,
        advanced=True),
    "API_SERVER_HOST": _msg(
        "Host/bind address for the API server (default: 127.0.0.1). API_SERVER_KEY is still "
        "required even on loopback binds.", "API server host", None, advanced=True),
    "API_SERVER_MODEL_NAME": _msg(
        "Model name advertised on /v1/models. Defaults to the profile name (or 'arkos-agent' "
        "for the default profile). Useful for multi-user setups with OpenWebUI.",
        "API server model name", None, advanced=True),
    "GATEWAY_PROXY_URL": _msg(
        "URL of a remote Arkos API server to forward messages to (proxy mode). When set, the "
        "gateway handles platform I/O only — all agent work is delegated to the remote server. "
        "Use for Docker E2EE containers that relay to a host agent. Also configurable via "
        "gateway.proxy_url in config.yaml.",
        "Remote Arkos API server URL (e.g. http://192.168.1.100:8642)", None, advanced=True),
    "GATEWAY_PROXY_KEY": _msg(
        "Bearer token for authenticating with the remote Arkos API server (proxy mode). Must "
        "match the API_SERVER_KEY on the remote host.", "Remote API server auth key", None,
        password=True, advanced=True),
    "WEBHOOK_ENABLED": _msg(
        "Enable the webhook platform adapter for receiving events from GitHub, GitLab, etc.",
        "Enable webhooks (true/false)", None),
    "WEBHOOK_PORT": _msg("Port for the webhook HTTP server (default: 8644).", "Webhook port", None),
    "WEBHOOK_SECRET": _msg(
        "Global HMAC secret for webhook signature validation (overridable per route in "
        "config.yaml).", "Webhook secret", None, password=True),
    "SUDO_PASSWORD": _setting(
        "Sudo password for terminal commands requiring root access; set to an explicit empty "
        "string to try empty without prompting", "Sudo password", None, password=True),
    "ARKOS_PREFILL_MESSAGES_FILE": _setting(
        "Path to JSON file with ephemeral prefill messages for few-shot priming",
        "Prefill messages file path", None),
    "ARKOS_EPHEMERAL_SYSTEM_PROMPT": _setting(
        "Ephemeral system prompt injected at API-call time (never persisted to sessions)",
        "Ephemeral system prompt", None),
}
