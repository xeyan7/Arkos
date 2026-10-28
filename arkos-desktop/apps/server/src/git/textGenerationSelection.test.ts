import { describe, expect, it } from "vitest";
import { resolveTextGenerationInputForSelection } from "./textGenerationSelection.ts";
describe("resolveTextGenerationInputForSelection", () => {
    it("routes Claude provider instances directly to text generation", () => {
        expect(resolveTextGenerationInputForSelection({
            provider: "arkos",
            instanceId: "claude_work",
            model: "claude-opus-4-6",
        }, {
            arkos: {
                homePath: "/tmp/claude-work",
                environment: { ANTHROPIC_AUTH_TOKEN: "token" },
            },
        })).toEqual({
            modelSelection: {
                provider: "arkos",
                instanceId: "claude_work",
                model: "claude-opus-4-6",
            },
            providerOptions: {
                arkos: {
                    homePath: "/tmp/claude-work",
                    environment: { ANTHROPIC_AUTH_TOKEN: "token" },
                },
            },
        });
    });
    it("uses the resolved instance driver as the routing authority", () => {
        expect(resolveTextGenerationInputForSelection({
            provider: "arkos",
            instanceId: "work",
            model: "claude-opus-4-6",
            options: { reasoningEffort: "high" },
        }, { arkos: { homePath: "/tmp/claude-work" } }, "arkos")).toEqual({
            modelSelection: {
                provider: "arkos",
                instanceId: "work",
                model: "claude-opus-4-6",
            },
            providerOptions: { arkos: { homePath: "/tmp/claude-work" } },
        });
    });
});
