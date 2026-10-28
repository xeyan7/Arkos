import type { ModelSelection, ProviderKind } from "@arkos/contracts";
import { describe, expect, it } from "vitest";
import { resolveAuxiliaryTextGenerationSelection, supportsTextGeneration, } from "./textGenerationCapabilities";
describe("auxiliary text-generation capabilities", () => {
    it.each(["arkos", "arkos", "arkos", "arkos"] satisfies ProviderKind[])("falls back to configured text generation for unsupported %s chats", (provider) => {
        const modelSelection = {
            instanceId: `${provider}_work`,
            model: `${provider}-model`,
        } as ModelSelection;
        expect(supportsTextGeneration(provider)).toBe(false);
        expect(resolveAuxiliaryTextGenerationSelection({ provider, modelSelection })).toBeNull();
    });
    it.each(["arkos", "arkos", "arkos", "arkos", "arkos"] satisfies ProviderKind[])("preserves the exact %s instance override", (provider) => {
        const modelSelection = {
            instanceId: `${provider}_work`,
            model: `${provider}-model`,
        } as ModelSelection;
        expect(resolveAuxiliaryTextGenerationSelection({ provider, modelSelection })).toBe(modelSelection);
    });
});
