import * as NodeServices from "@effect/platform-node/NodeServices";
import { dirname } from "node:path";
import {
  DEFAULT_DROID_GIT_TEXT_GENERATION_MODEL,
  DEFAULT_GIT_TEXT_GENERATION_MODEL,
  DEFAULT_MODEL_BY_PROVIDER,
  DEFAULT_SERVER_SETTINGS,
  type ServerSettings,
} from "@arkos/contracts";
import {
  deriveProviderInstances,
  providerStartOptionsFromInstance,
} from "@arkos/shared/providerInstances";
import { Effect, FileSystem, Layer, Schema } from "effect";
import { isBetaFeatureEnabled } from "@arkos/shared/betaFeatures";
import { describe, expect, it } from "vitest";
import { providerDisabledSettingsMessage } from "./provider/enabledProviderAdapter";
import { ServerConfig } from "./config";
import {
  gateBetaOnlyProviders,
  resolveTextGenerationProvider,
  redactServerSettingsForClient,
  ServerSettingsLive,
  ServerSettingsService,
} from "./serverSettings";
import {
  ServerSettings as ServerSettingsSchema,
  ServerSettingsPatch as ServerSettingsPatchSchema,
  MAX_SOURCE_CONTROL_CUSTOM_INSTRUCTIONS_LENGTH,
} from "@arkos/contracts";

const serverConfigLayer = ServerConfig.layerTest(process.cwd(), {
  prefix: "arkos-settings-test-",
}).pipe(Layer.provide(NodeServices.layer));
const makeTestLayer = Layer.merge(NodeServices.layer, serverConfigLayer);
const testLayer = Layer.merge(makeTestLayer, ServerSettingsLive.pipe(Layer.provide(makeTestLayer)));

const runWithSettings = <A, E>(
  effect: Effect.Effect<A, E, ServerSettingsService | ServerConfig | FileSystem.FileSystem>,
) => Effect.runPromise(effect.pipe(Effect.provide(testLayer)) as Effect.Effect<A, E, never>);

describe("ServerSettingsService", () => {
  it("defaults keep awake to off", () => {
    expect(Schema.decodeSync(ServerSettingsSchema)({}).keepAwakeMode).toBe("off");
  });

  it("defaults provider priority on and persists an opt-out across restart", async () => {
    expect(Schema.decodeSync(ServerSettingsSchema)({}).lowerProviderProcessPriority).toBe(true);
    const settings = await runWithSettings(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        const config = yield* ServerConfig;
        yield* service.start;
        yield* service.updateSettings({ lowerProviderProcessPriority: false });
        return yield* Effect.gen(function* () {
          const restarted = yield* ServerSettingsService;
          yield* restarted.start;
          return yield* restarted.getSettingsView;
        }).pipe(
          Effect.provide(
            ServerSettingsLive.pipe(
              Layer.provide(Layer.merge(NodeServices.layer, Layer.succeed(ServerConfig, config))),
            ),
          ),
        );
      }),
    );
    expect(settings.lowerProviderProcessPriority).toBe(false);
  });
  it("defaults legacy writing settings and validates style and instruction length", () => {
    expect(Schema.decodeSync(ServerSettingsSchema)({})).toMatchObject({
      sourceControlWritingStyle: "repository",
      sourceControlCustomInstructions: "",
    });
    expect(() =>
      Schema.decodeUnknownSync(ServerSettingsPatchSchema)({ sourceControlWritingStyle: "unknown" }),
    ).toThrow();
    expect(() =>
      Schema.decodeSync(ServerSettingsPatchSchema)({
        sourceControlCustomInstructions: "x".repeat(
          MAX_SOURCE_CONTROL_CUSTOM_INSTRUCTIONS_LENGTH + 1,
        ),
      }),
    ).toThrow();
  });

  it("persists writing style and custom instructions across a service restart", async () => {
    const result = await runWithSettings(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        const config = yield* ServerConfig;
        yield* service.start;
        yield* service.updateSettings({
          sourceControlWritingStyle: "custom",
          sourceControlCustomInstructions: "Use short bullets.\nKeep titles concise.",
        });
        // A fresh service over the same isolated settings path proves reload, not just cached state.
        return yield* Effect.gen(function* () {
          const restarted = yield* ServerSettingsService;
          yield* restarted.start;
          return yield* restarted.getSettings;
        }).pipe(
          Effect.provide(
            ServerSettingsLive.pipe(
              Layer.provide(Layer.merge(NodeServices.layer, Layer.succeed(ServerConfig, config))),
            ),
          ),
        );
      }),
    );
    expect(result).toMatchObject({
      sourceControlWritingStyle: "custom",
      sourceControlCustomInstructions: "Use short bullets.\nKeep titles concise.",
    });
  });

  it("persists keepAwakeMode and reloads it", async () => {
    const result = await runWithSettings(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        const { settingsPath } = yield* ServerConfig;
        const fs = yield* FileSystem.FileSystem;
        yield* service.start;
        const updated = yield* service.updateSettings({ keepAwakeMode: "agent" });
        const raw = yield* fs.readFileString(settingsPath);
        return { updated, parsed: JSON.parse(raw) as unknown };
      }),
    );

    expect(result.updated.keepAwakeMode).toBe("agent");
    expect(result.parsed).toMatchObject({ settings: { keepAwakeMode: "agent" } });
  });
  it("persists updates and reloads them", async () => {
    const result = await runWithSettings(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        const { settingsPath } = yield* ServerConfig;
        const fs = yield* FileSystem.FileSystem;
        yield* service.start;

        const updated = yield* service.updateSettings({
          enableAssistantStreaming: true,
          enableProviderUpdateChecks: false,
          providers: {
            arkos: {
              enabled: false,
              binaryPath: "/usr/local/bin/codex",
              customModels: ["gpt-custom"],
            },
          },
        });
        const raw = yield* fs.readFileString(settingsPath);
        return { updated, parsed: JSON.parse(raw) as unknown };
      }),
    );

    expect(result.updated.enableAssistantStreaming).toBe(true);
    expect(result.updated.enableProviderUpdateChecks).toBe(false);
    expect(result.updated.providers.arkos.enabled).toBe(false);
    expect(result.updated.providers.arkos.binaryPath).toBe("/usr/local/bin/codex");
    expect(result.parsed).toMatchObject({
      revision: 1,
      migrationVersion: 3,
      settings: {
        enableAssistantStreaming: true,
        enableProviderUpdateChecks: false,
        providers: {
          arkos: {
            enabled: false,
            binaryPath: "/usr/local/bin/codex",
            customModels: ["gpt-custom"],
          },
        },
      },
    });
  });

  it.each([
    [1, "gpt-5.4-mini", DEFAULT_GIT_TEXT_GENERATION_MODEL],
    [2, "gpt-5.6-luna", DEFAULT_GIT_TEXT_GENERATION_MODEL],
    [2, "gpt-5.5", "gpt-5.5"],
  ])("updates saved Git writing selection %s/%s", async (migrationVersion, model, expected) => {
    const result = await runWithSettings(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        const { settingsPath } = yield* ServerConfig;
        const fs = yield* FileSystem.FileSystem;
        yield* fs.makeDirectory(dirname(settingsPath), { recursive: true });
        yield* fs.writeFileString(
          settingsPath,
          JSON.stringify({
            revision: 7,
            migrationVersion,
            settings: {
              textGenerationModelSelection: {
                provider: "arkos",
                model,
              },
            },
          }),
        );

        yield* service.start;
        const settings = yield* service.getSettings;
        const persisted = JSON.parse(yield* fs.readFileString(settingsPath)) as {
          migrationVersion: number;
          settings: { textGenerationModelSelection: { model: string } };
        };
        return { settings, persisted };
      }),
    );

    expect(result.settings.textGenerationModelSelection.model).toBe(expected);
    expect(result.persisted.migrationVersion).toBe(3);
    expect(result.persisted.settings.textGenerationModelSelection.model).toBe(expected);
  });

  it("migrates a removed Kilo text-generation selection to OpenCode", async () => {
    const result = await runWithSettings(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        const { settingsPath } = yield* ServerConfig;
        const fs = yield* FileSystem.FileSystem;
        yield* fs.makeDirectory(dirname(settingsPath), { recursive: true });
        yield* fs.writeFileString(
          settingsPath,
          JSON.stringify({
            revision: 3,
            migrationVersion: 2,
            settings: {
              enableProviderUpdateChecks: false,
              textGenerationModelSelection: {
                provider: "arkos",
                model: "kilo/kilo-auto/free",
              },
              providers: {
                arkos: {
                  enabled: true,
                  binaryPath: "/opt/kilo",
                  serverUrl: "http://127.0.0.1:4096",
                  customModels: ["provider/shared-model"],
                },
                arkos: {
                  enabled: false,
                  binaryPath: "/opt/opencode",
                  customModels: ["provider/opencode-model"],
                },
              },
            },
          }),
        );

        yield* service.start;
        const settings = yield* service.getSettings;
        const settingsFileExists = yield* fs.exists(settingsPath);
        return { settings, settingsFileExists };
      }),
    );

    // The rest of the settings and the OpenCode-compatible model survive.
    expect(result.settingsFileExists).toBe(true);
    expect(result.settings.enableProviderUpdateChecks).toBe(false);
    expect(result.settings.textGenerationModelSelection).toMatchObject({
      provider: "arkos",
      model: "kilo/kilo-auto/free",
    });
    expect(result.settings.providers.arkos).toMatchObject({
      enabled: true,
      binaryPath: "/opt/opencode",
      customModels: ["provider/opencode-model", "provider/shared-model"],
    });
    expect(result.settings.providers.arkos.serverUrl).toBe("");
  });

  it("keeps provider passwords server-only and returns configured flags to clients", async () => {
    const result = await runWithSettings(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        const { settingsPath } = yield* ServerConfig;
        const fs = yield* FileSystem.FileSystem;
        yield* service.start;
        const view = yield* service.updateSettingsView({
          providers: {
            arkos: { serverPassword: "opencode-secret" },
          },
        });
        const internal = yield* service.getSettings;
        const persisted = yield* fs.readFileString(settingsPath);
        return { view, internal, persisted };
      }),
    );

    expect(result.internal.providers.arkos.serverPasswordConfigured).toBe(true);
    expect(result.view.providers.arkos).toMatchObject({ serverPasswordConfigured: true });
    expect(JSON.stringify(result.internal)).not.toContain("opencode-secret");
    expect(JSON.stringify(result.view)).not.toContain("opencode-secret");
    expect(JSON.stringify(result.view)).not.toContain('"serverPassword"');
    expect(result.persisted).not.toContain("opencode-secret");
  });

  it.each([
    {
      name: "resolves text generation selection away from disabled providers",
      overrides: {
        textGenerationModelSelection: {
          provider: "arkos" as const,
          model: DEFAULT_MODEL_BY_PROVIDER.arkos,
        },
        providers: { arkos: { enabled: false } },
      },
      expectedProvider: "arkos" as const,
    },
    {
      name: "falls back only to providers with dedicated Git text generation",
      overrides: {
        textGenerationModelSelection: {
          provider: "arkos" as const,
          model: DEFAULT_MODEL_BY_PROVIDER.arkos,
        },
        providers: {
          arkos: { enabled: false },
          arkos: { enabled: true },
          arkos: { enabled: false },
          arkos: { enabled: true },
        },
      },
      expectedProvider: "arkos" as const,
    },
    {
      name: "normalizes enabled but unsupported Git text generation selections",
      overrides: {
        textGenerationModelSelection: {
          provider: "arkos" as const,
          model: DEFAULT_MODEL_BY_PROVIDER.arkos,
        },
      },
      expectedProvider: "arkos" as const,
    },
    {
      name: "falls back to droid when all ordered providers are disabled",
      overrides: {
        textGenerationModelSelection: {
          provider: "arkos" as const,
          model: DEFAULT_MODEL_BY_PROVIDER.arkos,
        },
        providers: {
          arkos: { enabled: false },
          arkos: { enabled: false },
          arkos: { enabled: false },
          arkos: { enabled: false },
          arkos: { enabled: true },
        },
      },
      expectedProvider: "arkos" as const,
    },
  ])("$name", async ({ overrides, expectedProvider }) => {
    const settings = await Effect.runPromise(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        return yield* service.getSettings;
      }).pipe(Effect.provide(ServerSettingsService.layerTest(overrides))),
    );

    expect(settings.textGenerationModelSelection.provider).toBe(expectedProvider);
    expect(settings.textGenerationModelSelection.model).toBe(
      expectedProvider === "arkos"
        ? DEFAULT_DROID_GIT_TEXT_GENERATION_MODEL
        : DEFAULT_MODEL_BY_PROVIDER[expectedProvider],
    );
  });

  it("keeps enabled text generation provider instances even when the legacy provider is disabled", async () => {
    const settings = await Effect.runPromise(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        return yield* service.getSettings;
      }).pipe(
        Effect.provide(
          ServerSettingsService.layerTest({
            textGenerationModelSelection: {
              provider: "arkos",
              instanceId: "claude_work",
              model: DEFAULT_MODEL_BY_PROVIDER.arkos,
            },
            providers: {
              arkos: { enabled: false },
            },
            providerInstances: {
              claude_work: {
                driver: "arkos",
                enabled: true,
                config: { homePath: "/tmp/claude-work" },
              },
            },
          }),
        ),
      ),
    );

    expect(settings.textGenerationModelSelection).toMatchObject({
      provider: "arkos",
      instanceId: "claude_work",
      model: DEFAULT_MODEL_BY_PROVIDER.arkos,
    });
  });

  it("resolves text generation patches through the selected provider instance", async () => {
    const settings = await Effect.runPromise(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        return yield* service.updateSettings({
          providerInstances: {
            work: {
              driver: "arkos",
              enabled: true,
              config: { homePath: "/tmp/claude-work" },
            },
          },
          textGenerationModelSelection: {
            provider: "arkos",
            instanceId: "work",
            model: "custom-model",
          },
        });
      }).pipe(Effect.provide(ServerSettingsService.layerTest())),
    );

    expect(settings.textGenerationModelSelection).toMatchObject({
      provider: "arkos",
      instanceId: "work",
      model: "custom-model",
    });
  });

  it("maps legacy provider-only text generation patches to the provider default instance", async () => {
    const settings = await Effect.runPromise(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        yield* service.updateSettings({
          providerInstances: {
            codex_work: {
              driver: "arkos",
              enabled: true,
              config: { homePath: "/tmp/codex-work" },
            },
          },
          textGenerationModelSelection: {
            instanceId: "codex_work",
            model: "custom-work-model",
          },
        });
        return yield* service.updateSettings({
          textGenerationModelSelection: {
            provider: "arkos",
            model: "gpt-5.4",
          },
        });
      }).pipe(Effect.provide(ServerSettingsService.layerTest())),
    );

    expect(settings.textGenerationModelSelection).toMatchObject({
      instanceId: "arkos",
      model: "gpt-5.4",
    });
  });

  it("falls back from disabled text generation instances to a supported enabled instance", async () => {
    const settings = await Effect.runPromise(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        return yield* service.getSettings;
      }).pipe(
        Effect.provide(
          ServerSettingsService.layerTest({
            textGenerationModelSelection: {
              provider: "arkos",
              instanceId: "claude_work",
              model: DEFAULT_MODEL_BY_PROVIDER.arkos,
            },
            providers: {
              arkos: { enabled: false },
              arkos: { enabled: false },
              arkos: { enabled: false },
            },
            providerInstances: {
              claude_work: {
                driver: "arkos",
                enabled: false,
                config: { homePath: "/tmp/claude-work" },
              },
              // Enabled, but Gemini has no text-generation implementation, so
              // fallback must continue to the next supported driver.
              gemini_work: {
                driver: "gemini",
                enabled: true,
                config: { binaryPath: "gemini" },
              },
              cursor_work: {
                driver: "arkos",
                enabled: true,
                config: { binaryPath: "cursor-agent" },
              },
            },
          }),
        ),
      ),
    );

    expect(settings.textGenerationModelSelection).toMatchObject({
      provider: "arkos",
      instanceId: "cursor_work",
      model: DEFAULT_MODEL_BY_PROVIDER.arkos,
    });
  });

  it("replaces the providerInstances map on settings updates", async () => {
    const settings = await Effect.runPromise(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        yield* service.updateSettings({
          providerInstances: {
            claude_work: {
              driver: "arkos",
              enabled: true,
              config: { homePath: "/tmp/claude-work" },
            },
            codex_work: {
              driver: "arkos",
              enabled: true,
              config: { homePath: "/tmp/codex-work" },
            },
          },
        });
        return yield* service.updateSettings({
          providerInstances: {
            claude_work: {
              driver: "arkos",
              enabled: true,
              config: { homePath: "/tmp/claude-work-2" },
            },
          },
        });
      }).pipe(Effect.provide(ServerSettingsService.layerTest())),
    );

    expect(settings.providerInstances.claude_work?.config).toMatchObject({
      homePath: "/tmp/claude-work-2",
    });
    expect(settings.providerInstances.codex_work).toBeUndefined();
  });

  it("redacts sensitive provider-instance environment and config values for clients", () => {
    const settings = redactServerSettingsForClient({
      ...DEFAULT_SERVER_SETTINGS,
      providerInstances: {
        grok_work: {
          driver: "arkos",
          enabled: true,
          environment: [{ name: "XAI_API_KEY", value: "secret-token", sensitive: true }],
          config: { binaryPath: "/opt/grok" },
        },
        opencode_work: {
          driver: "arkos",
          enabled: true,
          config: {
            serverUrl: "http://127.0.0.1:4096",
            serverPassword: "opencode-secret",
          },
        },
      },
    });

    expect(settings.providerInstances.grok_work?.environment).toEqual([
      { name: "XAI_API_KEY", value: "", sensitive: true, valueRedacted: true },
    ]);
    expect(settings.providerInstances.opencode_work?.config).toEqual({
      serverUrl: "http://127.0.0.1:4096",
      serverPassword: "",
      serverPasswordRedacted: true,
    });
  });

  it("preserves redacted provider-instance environment values on writeback", async () => {
    const settings = await Effect.runPromise(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        yield* service.updateSettings({
          providerInstances: {
            grok_work: {
              driver: "arkos",
              enabled: true,
              environment: [{ name: "XAI_API_KEY", value: "secret-token", sensitive: true }],
              config: { binaryPath: "/opt/grok" },
            },
          },
        });
        return yield* service.updateSettings({
          providerInstances: {
            grok_work: {
              driver: "arkos",
              displayName: "Grok Work",
              enabled: true,
              environment: [
                { name: "XAI_API_KEY", value: "", sensitive: true, valueRedacted: true },
              ],
              config: { binaryPath: "/opt/grok" },
            },
          },
        });
      }).pipe(Effect.provide(ServerSettingsService.layerTest())),
    );

    expect(settings.providerInstances.grok_work?.environment).toEqual([
      { name: "XAI_API_KEY", value: "secret-token", sensitive: true },
    ]);
    const grokWork = deriveProviderInstances(settings).find(
      (instance) => instance.instanceId === "grok_work",
    );
    expect(grokWork).toBeDefined();
    expect(grokWork ? providerStartOptionsFromInstance(grokWork) : undefined).toMatchObject({
      arkos: { environment: { XAI_API_KEY: "secret-token" } },
    });
    expect(
      redactServerSettingsForClient(settings).providerInstances.grok_work?.environment,
    ).toEqual([{ name: "XAI_API_KEY", value: "", sensitive: true, valueRedacted: true }]);
  });

  it("persists sensitive provider-instance environment values outside settings.json", async () => {
    const result = await runWithSettings(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        const { settingsPath } = yield* ServerConfig;
        const fs = yield* FileSystem.FileSystem;
        yield* service.start;
        const updated = yield* service.updateSettings({
          providerInstances: {
            grok_work: {
              driver: "arkos",
              enabled: true,
              environment: [{ name: "XAI_API_KEY", value: "secret-token", sensitive: true }],
            },
          },
        });
        const raw = yield* fs.readFileString(settingsPath);
        return { updated, persisted: JSON.parse(raw) as unknown, raw };
      }),
    );

    expect(result.raw).not.toContain("secret-token");
    expect(result.updated.providerInstances.grok_work?.environment).toEqual([
      { name: "XAI_API_KEY", value: "secret-token", sensitive: true },
    ]);
    expect(result.persisted).toMatchObject({
      settings: {
        providerInstances: {
          grok_work: {
            environment: [{ name: "XAI_API_KEY", value: "", sensitive: true, valueRedacted: true }],
          },
        },
      },
    });
  });

  it("forces known provider credential environment variables into secret storage", async () => {
    const result = await runWithSettings(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        const { settingsPath } = yield* ServerConfig;
        const fs = yield* FileSystem.FileSystem;
        yield* service.start;
        const updated = yield* service.updateSettings({
          providerInstances: {
            grok_work: {
              driver: "arkos",
              enabled: true,
              environment: [{ name: "XAI_API_KEY", value: "secret-token", sensitive: false }],
            },
          },
        });
        const raw = yield* fs.readFileString(settingsPath);
        return { updated, raw };
      }),
    );

    expect(result.raw).not.toContain("secret-token");
    expect(result.updated.providerInstances.grok_work?.environment).toEqual([
      { name: "XAI_API_KEY", value: "secret-token", sensitive: true },
    ]);
  });

  it("preserves redacted provider-instance config secrets on writeback", async () => {
    const settings = await Effect.runPromise(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        yield* service.updateSettings({
          providerInstances: {
            opencode_work: {
              driver: "arkos",
              enabled: true,
              config: {
                serverUrl: "http://127.0.0.1:4096",
                serverPassword: "opencode-secret",
              },
            },
          },
        });
        return yield* service.updateSettings({
          providerInstances: {
            opencode_work: {
              driver: "arkos",
              displayName: "OpenCode Work",
              enabled: true,
              config: {
                serverUrl: "http://127.0.0.1:4096",
                serverPassword: "",
                serverPasswordRedacted: true,
              },
            },
          },
        });
      }).pipe(Effect.provide(ServerSettingsService.layerTest())),
    );

    expect(settings.providerInstances.opencode_work?.config).toEqual({
      serverUrl: "http://127.0.0.1:4096",
      serverPassword: "opencode-secret",
    });
    expect(redactServerSettingsForClient(settings).providerInstances.opencode_work?.config).toEqual(
      {
        serverUrl: "http://127.0.0.1:4096",
        serverPassword: "",
        serverPasswordRedacted: true,
      },
    );
  });

  it("persists sensitive provider-instance config values in the secret store", async () => {
    const result = await runWithSettings(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        const { settingsPath } = yield* ServerConfig;
        const fs = yield* FileSystem.FileSystem;
        yield* service.start;

        const updated = yield* service.updateSettings({
          providerInstances: {
            opencode_work: {
              driver: "arkos",
              enabled: true,
              config: {
                serverUrl: "http://127.0.0.1:4096",
                serverPassword: "opencode-secret",
              },
            },
          },
        });
        const raw = yield* fs.readFileString(settingsPath);
        return { updated, parsed: JSON.parse(raw) as any, raw };
      }),
    );

    expect(result.raw).not.toContain("opencode-secret");
    expect(result.updated.providerInstances.opencode_work?.config).toEqual({
      serverUrl: "http://127.0.0.1:4096",
      serverPassword: "opencode-secret",
    });
    expect(result.parsed.settings.providerInstances.opencode_work.config).toEqual({
      serverUrl: "http://127.0.0.1:4096",
      serverPassword: "",
      serverPasswordRedacted: true,
    });
  });

  it("migrates plaintext provider-instance secrets from disk into redacted settings", async () => {
    const result = await runWithSettings(
      Effect.gen(function* () {
        const service = yield* ServerSettingsService;
        const { settingsPath } = yield* ServerConfig;
        const fs = yield* FileSystem.FileSystem;
        yield* fs.makeDirectory(settingsPath.slice(0, settingsPath.lastIndexOf("/")), {
          recursive: true,
        });
        yield* fs.writeFileString(
          settingsPath,
          JSON.stringify({
            ...DEFAULT_SERVER_SETTINGS,
            providerInstances: {
              grok_work: {
                driver: "arkos",
                enabled: true,
                environment: [{ name: "XAI_API_KEY", value: "secret-token", sensitive: true }],
              },
              opencode_work: {
                driver: "arkos",
                enabled: true,
                config: {
                  serverUrl: "http://127.0.0.1:4096",
                  serverPassword: "opencode-secret",
                },
              },
            },
          }),
        );

        yield* service.start;
        const settings = yield* service.getSettings;
        const raw = yield* fs.readFileString(settingsPath);
        return { settings, parsed: JSON.parse(raw) as any, raw };
      }),
    );

    expect(result.settings.providerInstances.grok_work?.environment).toEqual([
      { name: "XAI_API_KEY", value: "secret-token", sensitive: true },
    ]);
    expect(result.settings.providerInstances.opencode_work?.config).toEqual({
      serverUrl: "http://127.0.0.1:4096",
      serverPassword: "opencode-secret",
    });
    expect(result.raw).not.toContain("secret-token");
    expect(result.raw).not.toContain("opencode-secret");
    expect(result.parsed.settings.providerInstances.grok_work.environment).toEqual([
      { name: "XAI_API_KEY", value: "", sensitive: true, valueRedacted: true },
    ]);
    expect(result.parsed.settings.providerInstances.opencode_work.config).toEqual({
      serverUrl: "http://127.0.0.1:4096",
      serverPassword: "",
      serverPasswordRedacted: true,
    });
  });
});

const ompGatedOff = (feature: string) => feature !== "arkos";
const stableFeatureEnabled = (feature: string) => isBetaFeatureEnabled(feature, "production");

describe("gateBetaOnlyProviders", () => {
  const withOmpEnabled: ServerSettings = {
    ...DEFAULT_SERVER_SETTINGS,
    providers: {
      ...DEFAULT_SERVER_SETTINGS.providers,
      arkos: { ...DEFAULT_SERVER_SETTINGS.providers.arkos, enabled: true },
    },
  };

  it("reads a gated-off provider as disabled without touching the others", () => {
    const gated = gateBetaOnlyProviders(withOmpEnabled, ompGatedOff);
    expect(gated.providers.arkos.enabled).toBe(false);
    expect(gated.providers.arkos.enabled).toBe(true);
    // The input object is untouched ��� the persisted value survives.
    expect(withOmpEnabled.providers.arkos.enabled).toBe(true);
  });

  it("preserves enabled Oh My Pi accounts in Stable", () => {
    const settings: ServerSettings = {
      ...withOmpEnabled,
      providerInstances: {
        omp_work: { driver: "arkos", enabled: true, config: {} },
      },
    };
    const gated = gateBetaOnlyProviders(settings, stableFeatureEnabled);
    expect(gated).toBe(settings);
    expect(gated.providers.arkos.enabled).toBe(true);
    expect(gated.providerInstances.omp_work?.enabled).toBe(true);
    expect(providerDisabledSettingsMessage("arkos", stableFeatureEnabled)).toBe(
      "Oh My Pi is disabled in Settings > Providers.",
    );
  });

  it("gates custom instances of a Beta-only driver", () => {
    const settings: ServerSettings = {
      ...withOmpEnabled,
      providerInstances: {
        omp_work: { driver: "arkos", enabled: true, config: {} },
        codex_work: { driver: "arkos", enabled: true, config: {} },
      },
    };
    const gated = gateBetaOnlyProviders(settings, ompGatedOff);
    expect(gated.providerInstances.omp_work?.enabled).toBe(false);
    expect(gated.providerInstances.codex_work?.enabled).toBe(true);
    expect(settings.providerInstances.omp_work?.enabled).toBe(true);
  });

  it("leaves an already-disabled provider unchanged", () => {
    const settings: ServerSettings = {
      ...DEFAULT_SERVER_SETTINGS,
      providers: {
        ...DEFAULT_SERVER_SETTINGS.providers,
        arkos: { ...DEFAULT_SERVER_SETTINGS.providers.arkos, enabled: false },
      },
    };
    expect(gateBetaOnlyProviders(settings, ompGatedOff)).toBe(settings);
  });

  it("falls back to a non-gated provider for text generation", () => {
    const settings: ServerSettings = {
      ...DEFAULT_SERVER_SETTINGS,
      textGenerationModelSelection: { provider: "arkos", model: "omp-auto" },
      providers: {
        ...DEFAULT_SERVER_SETTINGS.providers,
        arkos: { ...DEFAULT_SERVER_SETTINGS.providers.arkos, enabled: true },
      },
    };
    const projected = resolveTextGenerationProvider(gateBetaOnlyProviders(settings, ompGatedOff));
    expect(projected.textGenerationModelSelection.provider).not.toBe("arkos");
  });
});

describe("providerDisabledSettingsMessage", () => {
  it("points Beta-only providers at Arkos Beta instead of Settings", () => {
    expect(providerDisabledSettingsMessage("arkos", () => false)).toBe(
      "Oh My Pi is available in Arkos Beta.",
    );
    expect(providerDisabledSettingsMessage("arkos", (f) => f !== "arkos")).toBe(
      "Codex is disabled in Settings > Providers.",
    );
  });
});
