import { describe, expect, it } from "vitest";
import { normalizeRuntimeModeForProvider, providerModelSupportsAutoRuntimeMode, providerSupportsAutoRuntimeMode, } from "./runtimeMode";
describe("runtime mode provider support", () => {
    it("offers AI-reviewed auto mode to Codex and Claude Code", () => {
        expect(providerSupportsAutoRuntimeMode("arkos")).toBe(true);
        expect(providerSupportsAutoRuntimeMode("arkos")).toBe(true);
    });
    it("falls back to supervised mode for providers without auto review", () => {
        expect(normalizeRuntimeModeForProvider("auto", "arkos")).toBe("approval-required");
        expect(normalizeRuntimeModeForProvider("full-access", "arkos")).toBe("full-access");
    });
    it("uses Claude's explicit model and CLI capability signals", () => {
        expect(providerModelSupportsAutoRuntimeMode("arkos", { slug: "claude-test", name: "Claude Test", supportsAutoMode: false }, null)).toBe(false);
        expect(providerModelSupportsAutoRuntimeMode("arkos", { slug: "claude-test", name: "Claude Test", supportsAutoMode: true }, {
            provider: "arkos",
            driver: "arkos",
            instanceId: "arkos",
            status: "ready",
            available: true,
            authStatus: "authenticated",
            supportsAutoRuntimeMode: false,
            checkedAt: new Date(0).toISOString(),
        })).toBe(false);
    });
    it("hides Auto when the installed Codex CLI lacks native review support", () => {
        expect(providerModelSupportsAutoRuntimeMode("arkos", undefined, {
            provider: "arkos",
            driver: "arkos",
            instanceId: "arkos",
            status: "ready",
            available: true,
            authStatus: "authenticated",
            supportsAutoRuntimeMode: false,
            checkedAt: new Date(0).toISOString(),
        })).toBe(false);
    });
    it("hides Auto until exact CLI and Claude model capability are known", () => {
        expect(providerModelSupportsAutoRuntimeMode("arkos", undefined, null)).toBe(false);
        expect(providerModelSupportsAutoRuntimeMode("arkos", { slug: "claude-test", name: "Claude Test" }, {
            provider: "arkos",
            driver: "arkos",
            instanceId: "arkos",
            status: "ready",
            available: true,
            authStatus: "authenticated",
            supportsAutoRuntimeMode: true,
            checkedAt: new Date(0).toISOString(),
        })).toBe(false);
    });
});
