import { spawnSync } from "node:child_process";
import { describe, expect, it } from "vitest";
import { buildProviderChildEnvironment, registerProviderCredentialKey, withoutProviderCredentialEnvironment, } from "./providerChildEnvironment";
it("removes registered ambient provider credentials from account-scoped environments", () => {
    registerProviderCredentialKey("ACME_PROVIDER_TOKEN");
    expect(withoutProviderCredentialEnvironment({
        PATH: "/usr/bin",
        OPENAI_API_KEY: "ambient-openai",
        ACME_PROVIDER_TOKEN: "ambient-custom",
    })).toEqual({ PATH: "/usr/bin" });
});
describe("buildProviderChildEnvironment", () => {
    it("strips Arkos control-plane and inherited native capabilities", () => {
        const env = buildProviderChildEnvironment({
            provider: "arkos",
            baseEnv: {
                PATH: "/usr/bin",
                HOME: "/home/test",
                GEMINI_API_KEY: "provider-key",
                ARKOS_AUTH_TOKEN: "control-plane-secret",
                ARKOS_BROWSER_USE_PIPE_PATH: "/tmp/browser.sock",
                ARKOS_BROWSER_HOST_CAPABILITY: "private-desktop-capability",
                ARKOS_BROWSER_HOST_CAPABILITY_FD: "3",
                NODE_OPTIONS: "--require=/tmp/inject.js",
                NODE_REPL_SANDBOX_ALLOWED_UNIX_SOCKETS: "/tmp/other.sock",
            },
        });
        expect(env).toEqual({
            PATH: "/usr/bin",
            HOME: "/home/test",
            GEMINI_API_KEY: "provider-key",
        });
    });
    it("admits only explicitly granted capability keys", () => {
        const env = buildProviderChildEnvironment({
            provider: "arkos",
            baseEnv: {
                ARKOS_AUTH_TOKEN: "control-plane-secret",
                ARKOS_BROWSER_USE_PIPE_PATH: "/tmp/browser.sock",
                NODE_REPL_SANDBOX_ALLOWED_UNIX_SOCKETS: "/tmp/browser.sock",
            },
            inheritedArkosKeys: ["ARKOS_BROWSER_USE_PIPE_PATH"],
            inheritedNativeCapabilityKeys: ["NODE_REPL_SANDBOX_ALLOWED_UNIX_SOCKETS"],
        });
        expect(env).toEqual({
            ARKOS_BROWSER_USE_PIPE_PATH: "/tmp/browser.sock",
            NODE_REPL_SANDBOX_ALLOWED_UNIX_SOCKETS: "/tmp/browser.sock",
        });
    });
    it("does not let overlays bypass the capability policy", () => {
        const env = buildProviderChildEnvironment({
            provider: "arkos",
            baseEnv: { PATH: "/usr/bin" },
            overrides: {
                OPENCODE_EXPERIMENTAL_WEBSOCKETS: "true",
                ARKOS_AUTH_TOKEN: "overlaid-control-plane-secret",
                NODE_OPTIONS: "--require=/tmp/inject.js",
            },
        });
        expect(env).toEqual({
            PATH: "/usr/bin",
            OPENCODE_EXPERIMENTAL_WEBSOCKETS: "true",
        });
    });
    it.each([
        ["claude", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"],
        ["arkos", "CURSOR_API_KEY", "FACTORY_API_KEY"],
        ["arkos", "FACTORY_API_KEY", "XAI_API_KEY"],
        ["arkos", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"],
        ["arkos", "XAI_API_KEY", "GOOGLE_API_KEY"],
    ] as const)("grants %s only its declared provider credential group", (provider, grantedKey, unrelatedKey) => {
        const env = buildProviderChildEnvironment({
            provider,
            baseEnv: {
                PATH: "/usr/bin",
                [grantedKey]: "native-provider-secret",
                [unrelatedKey]: "unrelated-provider-secret",
            },
        });
        expect(env[grantedKey]).toBe("native-provider-secret");
        expect(env[unrelatedKey]).toBeUndefined();
    });
    it.each(["claude", "arkos", "arkos", "arkos", "arkos"] as const)("does not leak OpenAI credentials into restricted %s children", (provider) => {
        const env = buildProviderChildEnvironment({
            provider,
            baseEnv: {
                PATH: "/usr/bin",
                OPENAI_API_KEY: "unrelated-openai-secret",
            },
        });
        expect(env.OPENAI_API_KEY).toBeUndefined();
    });
    it.each(["arkos", "arkos", "arkos"] as const)("preserves upstream credential discovery for multi-provider %s", (provider) => {
        const env = buildProviderChildEnvironment({
            provider,
            baseEnv: {
                ANTHROPIC_API_KEY: "anthropic-secret",
                GEMINI_API_KEY: "gemini-secret",
                OPENAI_API_KEY: "openai-secret",
            },
        });
        expect(env.ANTHROPIC_API_KEY).toBe("anthropic-secret");
        expect(env.GEMINI_API_KEY).toBe("gemini-secret");
        expect(env.OPENAI_API_KEY).toBe("openai-secret");
    });
    it("keeps stripped authority absent in descendants", () => {
        const env = buildProviderChildEnvironment({
            provider: "arkos",
            baseEnv: {
                XAI_API_KEY: "grok-secret",
                ANTHROPIC_API_KEY: "unrelated-secret",
                ARKOS_AUTH_TOKEN: "control-plane-secret",
            },
        });
        const descendantScript = "process.stdout.write(JSON.stringify({ xai: process.env.XAI_API_KEY, anthropic: process.env.ANTHROPIC_API_KEY, arkos: process.env.ARKOS_AUTH_TOKEN }))";
        const parentScript = `const { spawnSync } = require("node:child_process"); const result = spawnSync(process.execPath, ["-e", ${JSON.stringify(descendantScript)}], { env: process.env, encoding: "utf8" }); process.stdout.write(result.stdout); process.stderr.write(result.stderr); process.exit(result.status ?? 1);`;
        const result = spawnSync(process.execPath, ["-e", parentScript], {
            env,
            encoding: "utf8",
        });
        expect(result.status).toBe(0);
        expect(JSON.parse(result.stdout)).toEqual({ xai: "grok-secret" });
    });
    it("matches declared provider credential grants case-insensitively", () => {
        const env = buildProviderChildEnvironment({
            provider: "claude",
            baseEnv: {
                anthropic_api_key: "native-provider-secret",
                gemini_api_key: "unrelated-provider-secret",
            },
        });
        expect(env.anthropic_api_key).toBe("native-provider-secret");
        expect(env.gemini_api_key).toBeUndefined();
    });
});
