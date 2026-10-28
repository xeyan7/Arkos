// FILE: appSettings.test.ts
// Purpose: Verifies app settings normalization, model options, and provider dispatch options.
// Layer: Web settings tests
// Exports: Vitest suites for appSettings.ts
import { Schema } from "effect";
import { DEFAULT_MODEL_BY_PROVIDER, DEFAULT_SERVER_SETTINGS_VIEW, ProviderInstanceId, } from "@arkos/contracts";
import { describe, expect, it } from "vitest";
import { AppSettingsSchema, applyLocalAppSettingsPatch, appSettingsPatchToServerSettingsPatch, buildInitialServerSettingsMigrationPatch, DEFAULT_CHAT_FONT_SIZE_PX, DEFAULT_FOLLOW_UP_BEHAVIOR, DEFAULT_TERMINAL_FONT_SIZE_PX, didProviderCommandDiscoverySettingsChange, didProviderEnablementChange, getAppModelOptions, getCustomBinaryPathForProvider, getCustomBinaryPathForProviderInstance, getDefaultNativeFontSmoothing, getCustomModelsByProvider, getCustomModelsForProviderInstance, getProviderInstanceOptions, getUnsupportedProviderInstanceOptions, getServerDisabledProviders, isGitTextGenerationSettingsDirty, getProviderStartOptions, mergeProviderStartOptions, normalizeChatFontSizePx, normalizeInitialStoredAppSettingsForServerMigration, normalizeStoredAppSettings, normalizeTerminalFontFamily, normalizeTerminalFontSizePx, resolveAppModelSelection, resolveFollowUpDispatchMode, resolveSelectableProviderInstanceId, resolveTerminalFontFamilyStack, serverSettingsToAppSettings, } from "./appSettings";
describe("provider process priority settings", () => {
    it("defaults on and forwards explicit opt-out and reset to the server", () => {
        expect(Schema.decodeSync(AppSettingsSchema)({}).lowerProviderProcessPriority).toBe(true);
        expect(appSettingsPatchToServerSettingsPatch({ lowerProviderProcessPriority: false })).toEqual({
            lowerProviderProcessPriority: false,
        });
        expect(appSettingsPatchToServerSettingsPatch({ lowerProviderProcessPriority: true })).toEqual({
            lowerProviderProcessPriority: true,
        });
    });
});
describe("source control writing settings", () => {
    it("defaults old settings to repository conventions and saves both preferences to the server", () => {
        const settings = Schema.decodeSync(AppSettingsSchema)({});
        expect(settings.sourceControlWritingStyle).toBe("repository");
        expect(settings.sourceControlCustomInstructions).toBe("");
        expect(appSettingsPatchToServerSettingsPatch({
            sourceControlWritingStyle: "custom",
            sourceControlCustomInstructions: "Use short bullets.",
        })).toEqual({
            sourceControlWritingStyle: "custom",
            sourceControlCustomInstructions: "Use short bullets.",
        });
        expect(appSettingsPatchToServerSettingsPatch({ sourceControlWritingStyle: "conventional" })).toEqual({ sourceControlWritingStyle: "conventional" });
        expect(appSettingsPatchToServerSettingsPatch({ sourceControlCustomInstructions: "" })).toEqual({
            sourceControlCustomInstructions: "",
        });
    });
});
describe("computer control defaults", () => {
    it("leaves computer control off until a preference is explicitly saved", () => {
        expect(AppSettingsSchema.makeUnsafe({}).computerControlEnabled).toBe(false);
        const decoded = Schema.decodeUnknownSync(AppSettingsSchema)({ autoOpenComputerPane: false });
        expect(normalizeStoredAppSettings(decoded).computerControlEnabled).toBe(false);
    });
    it("migrates the legacy per-chat computer control default", () => {
        const decoded = Schema.decodeUnknownSync(AppSettingsSchema)({
            allowComputerControlInNewChats: true,
        });
        const normalized = normalizeStoredAppSettings(decoded);
        expect(normalized.computerControlEnabled).toBe(true);
        expect(normalized).not.toHaveProperty("allowComputerControlInNewChats");
    });
    it("defaults the in-chat preview to the compact footprint", () => {
        expect(AppSettingsSchema.makeUnsafe({}).computerPreviewSize).toBe("compact");
        const decoded = Schema.decodeUnknownSync(AppSettingsSchema)({ computerPreviewSize: "large" });
        expect(normalizeStoredAppSettings(decoded).computerPreviewSize).toBe("large");
    });
});
describe("resolveFollowUpDispatchMode", () => {
    it("uses the selected behavior only while a turn is live", () => {
        expect(resolveFollowUpDispatchMode({
            behavior: "steer",
            hasLiveTurn: false,
        })).toBe("queue");
        expect(resolveFollowUpDispatchMode({
            behavior: "steer",
            hasLiveTurn: true,
        })).toBe("steer");
    });
    it("uses Ctrl/Cmd+Enter as a one-message inversion", () => {
        expect(resolveFollowUpDispatchMode({
            behavior: "queue",
            hasLiveTurn: true,
            useOppositeBehavior: true,
        })).toBe("steer");
        expect(resolveFollowUpDispatchMode({
            behavior: "steer",
            hasLiveTurn: true,
            useOppositeBehavior: true,
        })).toBe("queue");
    });
});
describe("getAppModelOptions", () => {
    it("does not expose Anthropic models in Pi before authenticated discovery", () => {
        expect(getAppModelOptions("arkos", [])).toEqual([]);
    });
    it("appends saved custom models after the built-in options", () => {
        const options = getAppModelOptions("arkos", ["custom/internal-model"]);
        expect(options.map((option) => option.slug)).toEqual([
            "gpt-6-astra",
            "gpt-6-sol",
            "gpt-6-luna",
            "gpt-5.5",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.3-codex",
            "gpt-5.3-codex-spark",
            "gpt-5.2-codex",
            "gpt-5.2",
            "custom/internal-model",
        ]);
    });
    it("keeps the currently selected custom model available even if it is no longer saved", () => {
        const options = getAppModelOptions("arkos", [], "custom/selected-model");
        expect(options.at(-1)).toEqual({
            slug: "custom/selected-model",
            name: "custom/selected-model",
            provider: "arkos",
            isCustom: true,
        });
    });
    it("keeps Cursor transport parameters out of selected-model hints", () => {
        const options = getAppModelOptions("arkos", [], "grok-4.5[thinking=true]");
        expect(options.filter((option) => option.slug.startsWith("grok-4.5")).map((option) => option.slug)).toEqual(["grok-4.5"]);
    });
});
describe("isGitTextGenerationSettingsDirty", () => {
    it("compares the normalized provider and model defaults", () => {
        const defaults = AppSettingsSchema.makeUnsafe({});
        expect(isGitTextGenerationSettingsDirty(defaults, defaults)).toBe(false);
        expect(isGitTextGenerationSettingsDirty({ ...defaults, textGenerationProvider: "arkos", textGenerationModel: "custom/model" }, defaults)).toBe(true);
    });
});
describe("code review sort", () => {
    it("defaults existing settings to newest and preserves a stored activity order", () => {
        const decode = Schema.decodeUnknownSync(AppSettingsSchema);
        expect(decode({}).githubInboxSort).toBe("created");
        expect(decode({ githubInboxSort: "updated" }).githubInboxSort).toBe("updated");
    });
});
describe("removed settings", () => {
    it("ignores a code review list width stored before widths became fractions", () => {
        const decoded = Schema.decodeUnknownSync(AppSettingsSchema)({
            githubInboxListWidth: 420,
            githubInboxKind: "issue",
        });
        expect(decoded).not.toHaveProperty("githubInboxListWidth");
        expect(decoded.githubInboxKind).toBe("issue");
    });
});
describe("environment panel defaults", () => {
    it("starts optional text sections disabled without overriding explicit preferences", () => {
        const defaults = AppSettingsSchema.makeUnsafe({});
        expect(defaults).toMatchObject({
            showEnvironmentInstructions: false,
            showEnvironmentNotepad: false,
        });
        const enabled = AppSettingsSchema.makeUnsafe({
            showEnvironmentInstructions: true,
            showEnvironmentNotepad: true,
        });
        expect(enabled).toMatchObject({
            showEnvironmentInstructions: true,
            showEnvironmentNotepad: true,
        });
    });
});
describe("resolveAppModelSelection", () => {
    it("preserves saved custom model slugs instead of falling back to the default", () => {
        expect(resolveAppModelSelection("arkos", {
            arkos: ["galapagos-alpha"],
        }, "galapagos-alpha")).toBe("galapagos-alpha");
    });
    it("falls back to the provider default when no model is selected", () => {
        expect(resolveAppModelSelection("arkos", {
            arkos: [],
        }, "")).toBe(DEFAULT_MODEL_BY_PROVIDER.arkos);
    });
});
describe("chat font size defaults", () => {
    it("clamps chat font size updates into the supported range", () => {
        expect(normalizeChatFontSizePx(9)).toBe(11);
        expect(normalizeChatFontSizePx(18.4)).toBe(18);
        expect(normalizeChatFontSizePx(Number.NaN)).toBe(DEFAULT_CHAT_FONT_SIZE_PX);
    });
});
describe("terminal font size defaults", () => {
    it("clamps terminal font size updates into the supported range", () => {
        expect(normalizeTerminalFontSizePx(8)).toBe(10);
        expect(normalizeTerminalFontSizePx(20.4)).toBe(20);
        expect(normalizeTerminalFontSizePx(99)).toBe(22);
        expect(normalizeTerminalFontSizePx(Number.NaN)).toBe(DEFAULT_TERMINAL_FONT_SIZE_PX);
    });
});
describe("terminal font family settings", () => {
    it("leaves the bundled terminal font stack active for empty values", () => {
        expect(resolveTerminalFontFamilyStack("")).toBeNull();
        expect(resolveTerminalFontFamilyStack("   ")).toBeNull();
    });
    it("quotes a single multi-word font and appends a monospace fallback", () => {
        expect(resolveTerminalFontFamilyStack("Fira Code")).toBe('"Fira Code", monospace');
        expect(resolveTerminalFontFamilyStack("Menlo")).toBe("Menlo, monospace");
    });
    it("preserves explicit font stacks while adding a generic fallback when missing", () => {
        expect(resolveTerminalFontFamilyStack('"Fira Code", Menlo')).toBe('"Fira Code", Menlo, monospace');
        expect(resolveTerminalFontFamilyStack('"Fira Code", ui-monospace')).toBe('"Fira Code", ui-monospace');
    });
    it("strips characters that could break the terminal font CSS variable", () => {
        expect(normalizeTerminalFontFamily("Fira; Code{}\n<>")).toBe("Fira Code");
    });
});
describe("normalizeStoredAppSettings", () => {
    it("defaults native font smoothing by platform", () => {
        expect(getDefaultNativeFontSmoothing("MacIntel")).toBe(true);
        expect(getDefaultNativeFontSmoothing("Win32")).toBe(false);
        expect(getDefaultNativeFontSmoothing("Linux x86_64")).toBe(false);
    });
    it("uses the current platform default for existing settings without a stored value", () => {
        const decodedSettings = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema))("{}");
        expect(decodedSettings.enableNativeFontSmoothing).toBe(getDefaultNativeFontSmoothing());
    });
    it("preserves an explicitly stored updated_at project sort order", () => {
        const decodedSettings = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema))(JSON.stringify({
            sidebarProjectSortOrder: "updated_at",
            chatFontSizePx: 99,
            terminalFontSizePx: 3,
            customCodexModels: [
                " custom/internal-model ",
                "gpt-5.4",
                "custom/internal-model",
                "5.3",
                "",
            ],
        }));
        expect(normalizeStoredAppSettings(decodedSettings)).toMatchObject({
            sidebarProjectSortOrder: "updated_at",
            chatFontSizePx: 18,
            terminalFontSizePx: 10,
            customCodexModels: ["custom/internal-model"],
        });
    });
    it("redacts provider instance secrets so plaintext never persists locally", () => {
        const decodedSettings = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema))(JSON.stringify({
            providerInstances: {
                grok_work: {
                    driver: "arkos",
                    environment: [
                        { name: "XAI_API_KEY", value: "super-secret", sensitive: true },
                        { name: "XAI_BASE_URL", value: "https://example.test", sensitive: false },
                    ],
                },
                opencode_work: {
                    driver: "arkos",
                    config: { serverUrl: "http://127.0.0.1:4096", serverPassword: "server-secret" },
                },
            },
        }));
        const normalized = normalizeStoredAppSettings(decodedSettings);
        expect(normalized.providerInstances.grok_work?.environment).toEqual([
            { name: "XAI_API_KEY", value: "", sensitive: true, valueRedacted: true },
            { name: "XAI_BASE_URL", value: "https://example.test", sensitive: false },
        ]);
        expect(normalized.providerInstances.opencode_work?.config).toEqual({
            serverUrl: "http://127.0.0.1:4096",
            serverPassword: "",
            serverPasswordRedacted: true,
        });
    });
    it("builds the initial server migration patch from legacy plaintext before storage redaction", () => {
        const decodedSettings = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema))(JSON.stringify({
            providerInstances: {
                grok_work: {
                    driver: "arkos",
                    environment: [{ name: "XAI_API_KEY", value: "super-secret", sensitive: true }],
                },
                opencode_work: {
                    driver: "arkos",
                    config: { serverUrl: "http://127.0.0.1:4096", serverPassword: "server-secret" },
                },
            },
        }));
        expect(buildInitialServerSettingsMigrationPatch(decodedSettings).providerInstances).toEqual({
            grok_work: {
                driver: "arkos",
                environment: [{ name: "XAI_API_KEY", value: "super-secret", sensitive: true }],
            },
            opencode_work: {
                driver: "arkos",
                config: { serverUrl: "http://127.0.0.1:4096", serverPassword: "server-secret" },
            },
        });
        expect(normalizeStoredAppSettings(decodedSettings).providerInstances).toEqual({
            grok_work: {
                driver: "arkos",
                environment: [{ name: "XAI_API_KEY", value: "", sensitive: true, valueRedacted: true }],
            },
            opencode_work: {
                driver: "arkos",
                config: {
                    serverUrl: "http://127.0.0.1:4096",
                    serverPassword: "",
                    serverPasswordRedacted: true,
                },
            },
        });
    });
    it("keeps legacy provider secrets until the server migration is committed", () => {
        const decodedSettings = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema))(JSON.stringify({
            providerInstances: {
                grok_work: {
                    driver: "arkos",
                    environment: [{ name: "XAI_API_KEY", value: "super-secret", sensitive: true }],
                },
                opencode_work: {
                    driver: "arkos",
                    config: { serverUrl: "http://127.0.0.1:4096", serverPassword: "server-secret" },
                },
            },
        }));
        expect(normalizeInitialStoredAppSettingsForServerMigration(decodedSettings, false).providerInstances).toEqual({
            grok_work: {
                driver: "arkos",
                environment: [{ name: "XAI_API_KEY", value: "super-secret", sensitive: true }],
            },
            opencode_work: {
                driver: "arkos",
                config: { serverUrl: "http://127.0.0.1:4096", serverPassword: "server-secret" },
            },
        });
        expect(normalizeInitialStoredAppSettingsForServerMigration(decodedSettings, true).providerInstances).toEqual({
            grok_work: {
                driver: "arkos",
                environment: [{ name: "XAI_API_KEY", value: "", sensitive: true, valueRedacted: true }],
            },
            opencode_work: {
                driver: "arkos",
                config: {
                    serverUrl: "http://127.0.0.1:4096",
                    serverPassword: "",
                    serverPasswordRedacted: true,
                },
            },
        });
    });
    it("drops default provider command names so they do not look like custom paths", () => {
        const decodedSettings = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema))(JSON.stringify({
            claudeBinaryPath: "claude",
            codexBinaryPath: "arkos",
            cursorBinaryPath: "cursor-agent",
            antigravityBinaryPath: "agy",
            grokBinaryPath: "arkos",
            droidBinaryPath: "arkos",
            openCodeBinaryPath: "arkos",
            piBinaryPath: "arkos",
        }));
        const normalized = normalizeStoredAppSettings(decodedSettings);
        expect(normalized).toMatchObject({
            claudeBinaryPath: "",
            codexBinaryPath: "",
            cursorBinaryPath: "",
            antigravityBinaryPath: "",
            grokBinaryPath: "",
            droidBinaryPath: "",
            openCodeBinaryPath: "",
            piBinaryPath: "",
            ompBinaryPath: "",
            ompAgentDir: "",
        });
        expect(getCustomBinaryPathForProvider(normalized, "arkos")).toBe("");
    });
});
describe("AppSettingsSchema", () => {
    it("keeps sent-message anchoring enabled for settings saved before the preference existed", () => {
        const decode = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema));
        expect(decode(JSON.stringify({ chatFontSizePx: 17 }))).toMatchObject({
            anchorSentMessagesToTop: true,
            chatFontSizePx: 17,
        });
    });
    it("preserves disabled sent-message anchoring across persistence until defaults are restored", () => {
        const codec = Schema.fromJsonString(AppSettingsSchema);
        const decode = Schema.decodeSync(codec);
        const defaults = decode("{}");
        const settings = applyLocalAppSettingsPatch(defaults, { anchorSentMessagesToTop: false });
        const restored = decode(Schema.encodeSync(codec)(settings));
        expect(restored).toMatchObject({ anchorSentMessagesToTop: false });
        expect(applyLocalAppSettingsPatch(restored, defaults)).toMatchObject({
            anchorSentMessagesToTop: true,
        });
    });
    it("opens Tasks as the list until the user picks the Kanban view", () => {
        const decode = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema));
        expect(decode(JSON.stringify({})).tasksViewMode).toBe("list");
        expect(decode(JSON.stringify({ tasksViewMode: "kanban" })).tasksViewMode).toBe("kanban");
    });
    it("migrates persisted Gemini provider settings to Antigravity", () => {
        const decode = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema));
        const decoded = decode(JSON.stringify({
            textGenerationProvider: "gemini",
            defaultProvider: "gemini",
            hiddenProviders: ["gemini"],
            providerOrder: ["arkos", "gemini"],
            hiddenModels: [{ provider: "gemini", slug: "gemini-3.1-pro-preview" }],
            geminiBinaryPath: "/custom/bin/gemini",
            customGeminiModels: ["gemini-custom-preview"],
        }));
        expect(decoded).toMatchObject({
            textGenerationProvider: "arkos",
            defaultProvider: "arkos",
            hiddenProviders: ["arkos"],
            providerOrder: ["arkos", "arkos"],
            hiddenModels: [{ provider: "arkos", slug: "gemini-3.1-pro-preview" }],
        });
        expect(normalizeStoredAppSettings(decoded)).toMatchObject({
            antigravityBinaryPath: "/custom/bin/gemini",
            customAntigravityModels: ["gemini-custom-preview"],
        });
        expect(normalizeStoredAppSettings(decoded)).not.toHaveProperty("geminiBinaryPath");
        expect(normalizeStoredAppSettings(decoded)).not.toHaveProperty("customGeminiModels");
    });
    it("migrates persisted Kilo provider settings without transferring them to OpenCode", () => {
        const decode = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema));
        const decoded = decode(JSON.stringify({
            textGenerationProvider: "arkos",
            defaultProvider: "arkos",
            hiddenProviders: ["arkos", "arkos"],
            providerOrder: ["arkos", "arkos", "arkos"],
            hiddenModels: [{ provider: "arkos", slug: "kilo/kilo-auto/free" }],
        }));
        // Single-value settings fall back to the runtime that hosted Kilo sessions;
        // list entries (hidden/disabled/order) are dropped so Kilo preferences do
        // not transfer onto the separate OpenCode subscription.
        expect(decoded).toMatchObject({
            textGenerationProvider: "arkos",
            defaultProvider: "arkos",
            hiddenProviders: ["arkos"],
            providerOrder: ["arkos", "arkos"],
            hiddenModels: [],
        });
    });
    it("drops unknown provider names from persisted lists instead of failing decode", () => {
        const decode = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema));
        const decoded = decode(JSON.stringify({
            hiddenProviders: ["some-future-provider", "arkos"],
            providerOrder: ["gemini", "arkos"],
            railUsageProviders: ["some-future-provider", "arkos", "gemini"],
            chatFontSizePx: 17,
        }));
        expect(decoded).toMatchObject({
            hiddenProviders: ["arkos"],
            providerOrder: ["arkos", "arkos"],
            railUsageProviders: ["arkos", "arkos"],
            chatFontSizePx: 17,
        });
    });
    it("migrates sidebar provider selections to their default account ids", () => {
        const decode = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema));
        expect(normalizeStoredAppSettings(decode("{}")).railUsageInstanceIds).toEqual([
            "arkos",
            "arkos",
        ]);
        expect(normalizeStoredAppSettings(decode(JSON.stringify({ railUsageProviders: ["gemini"] })))
            .railUsageInstanceIds).toEqual(["arkos"]);
        expect(normalizeStoredAppSettings(decode(JSON.stringify({ railUsageProviders: [] })))
            .railUsageInstanceIds).toEqual([]);
    });
    it("persists two Claude accounts and an explicit empty sidebar selection", () => {
        const codec = Schema.fromJsonString(AppSettingsSchema);
        const decode = Schema.decodeSync(codec);
        const updated = applyLocalAppSettingsPatch(decode("{}"), {
            railUsageInstanceIds: ["arkos", "claude_work"],
        });
        expect(normalizeStoredAppSettings(decode(Schema.encodeSync(codec)(updated))).railUsageInstanceIds).toEqual(["arkos", "claude_work"]);
        const withDisabledChoice = applyLocalAppSettingsPatch(updated, {
            railUsageInstanceIds: ["arkos", "claude_work", "arkos"],
        });
        expect(normalizeStoredAppSettings(decode(Schema.encodeSync(codec)(withDisabledChoice)))
            .railUsageInstanceIds).toEqual(["arkos", "claude_work", "arkos"]);
        const hidden = applyLocalAppSettingsPatch(updated, { railUsageInstanceIds: [] });
        expect(normalizeStoredAppSettings(decode(Schema.encodeSync(codec)(hidden))).railUsageInstanceIds).toEqual([]);
    });
    it("drops malformed sidebar account ids without resetting unrelated preferences", () => {
        const decode = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema));
        const decoded = decode(JSON.stringify({
            railUsageInstanceIds: ["claude_work", "invalid id", "", "../account"],
            chatFontSizePx: 17,
        }));
        expect(decoded.railUsageInstanceIds).toEqual(["claude_work"]);
        expect(decoded.chatFontSizePx).toBe(17);
    });
    it("drops rail ids this build does not know and ignores the retired classic-sidebar keys", () => {
        const decode = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema));
        const decoded = decode(JSON.stringify({
            sidebarLayout: "classic",
            railItemOrder: ["some-future-item", "kanban", "home"],
            hiddenRailItems: ["some-future-item", "studio"],
            sidebarNavOrder: ["some-future-item", "kanban"],
            hiddenSidebarNavItems: ["some-future-item"],
        }));
        expect(decoded).toMatchObject({
            railItemOrder: ["kanban", "home"],
            hiddenRailItems: ["studio"],
        });
        // Settings saved while the classic sidebar existed still decode; its keys are dropped.
        expect(decoded).not.toHaveProperty("sidebarLayout");
        expect(decoded).not.toHaveProperty("sidebarNavOrder");
        expect(decoded).not.toHaveProperty("hiddenSidebarNavItems");
    });
    it("defaults the Environment panel closed and preserves an explicit open preference", () => {
        const decode = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema));
        expect(decode("{}").environmentPanelDefaultOpen).toBe(false);
        expect(decode(JSON.stringify({ environmentPanelDefaultOpen: true })).environmentPanelDefaultOpen).toBe(true);
    });
    it("keeps usage popover details collapsed by default and preserves an explicit choice", () => {
        const decode = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema));
        expect(decode("{}").usageDetailsDefaultOpen).toBe(false);
        expect(decode("{}").usagePopoverShowResetCredits).toBe(true);
        expect(decode("{}").usagePopoverShowUsageLines).toBe(true);
        expect(decode(JSON.stringify({ usagePopoverShowUsageLines: false })).usagePopoverShowUsageLines).toBe(false);
        expect(decode(JSON.stringify({ usageDetailsDefaultOpen: true })).usageDetailsDefaultOpen).toBe(true);
    });
    it("preserves a disabled simulator auto-open preference across settings persistence", () => {
        const codec = Schema.fromJsonString(AppSettingsSchema);
        const decode = Schema.decodeSync(codec);
        const defaults = decode("{}");
        expect(defaults.autoOpenDevicePane).toBe(true);
        const settings = applyLocalAppSettingsPatch(defaults, { autoOpenDevicePane: false });
        expect(decode(Schema.encodeSync(codec)(settings)).autoOpenDevicePane).toBe(false);
    });
    it("fills decoding defaults for persisted settings that predate newer keys", () => {
        const decode = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema));
        expect(decode(JSON.stringify({
            codexBinaryPath: "/usr/local/bin/codex",
            confirmThreadDelete: false,
        }))).toMatchObject({
            claudeBinaryPath: "",
            uiDensity: "comfortable",
            chatFontSizePx: 13,
            terminalFontSizePx: 12,
            codexBinaryPath: "/usr/local/bin/codex",
            codexHomePath: "",
            grokBinaryPath: "",
            defaultThreadEnvMode: "local",
            confirmThreadDelete: false,
            confirmTerminalTabClose: true,
            desktopAppIcon: "default",
            useCustomTitleBar: true,
            enableAppSnap: false,
            appSnapShortcut: { kind: "both-option-keys" },
            appSnapPlaySound: true,
            enableAssistantStreaming: true,
            followUpBehavior: DEFAULT_FOLLOW_UP_BEHAVIOR,
            sidebarProjectSortOrder: "manual",
            sidebarThreadSortOrder: "updated_at",
            showGroupsSection: true,
            showAutomationRunThreads: true,
            timestampFormat: "locale",
            customCodexModels: [],
            customClaudeModels: [],
            customCursorModels: [],
            customGrokModels: [],
            customDroidModels: [],
            customOpenCodeModels: [],
            customPiModels: [],
            customOmpModels: [],
        });
    });
    it("migrates the former AppSnap feature flag", () => {
        const decode = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema));
        expect(normalizeStoredAppSettings(decode(JSON.stringify({ enableAppshots: true })))).toMatchObject({
            enableAppSnap: true,
        });
        expect(normalizeStoredAppSettings(decode(JSON.stringify({ enableAppshots: true })))).not.toHaveProperty("enableAppshots");
    });
});
describe("keepAwakeMode mapping", () => {
    it("defaults to off when absent from stored settings", () => {
        const decode = Schema.decodeSync(Schema.fromJsonString(AppSettingsSchema));
        expect(decode("{}").keepAwakeMode).toBe("off");
    });
    it("maps the server setting into app settings", () => {
        const mapped = serverSettingsToAppSettings({
            ...DEFAULT_SERVER_SETTINGS_VIEW,
            keepAwakeMode: "always",
        });
        expect(mapped.keepAwakeMode).toBe("always");
    });
    it("maps the app setting into a server patch", () => {
        expect(appSettingsPatchToServerSettingsPatch({ keepAwakeMode: "agent" })).toEqual({
            keepAwakeMode: "agent",
        });
        expect(appSettingsPatchToServerSettingsPatch({ enableAssistantStreaming: true })).not.toHaveProperty("keepAwakeMode");
    });
});
