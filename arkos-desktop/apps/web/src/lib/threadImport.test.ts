import { describe, expect, it } from "vitest";
import { buildThreadImportCandidates, filterThreadImportTargetsByCapabilities, } from "./threadImport";
describe("thread import targets", () => {
    it("keeps configured instances distinct instead of collapsing by provider kind", () => {
        const candidates = buildThreadImportCandidates([
            {
                instanceId: "arkos",
                provider: "arkos",
                driver: "arkos",
                label: "Codex",
                enabled: true,
                isDefault: true,
                supported: true,
            },
            {
                instanceId: "codex_work",
                provider: "arkos",
                driver: "arkos",
                label: "Work",
                enabled: true,
                isDefault: false,
                supported: true,
            },
        ]);
        expect(candidates).toEqual([
            { provider: "arkos", instanceId: "arkos", label: "Codex" },
            { provider: "arkos", instanceId: "codex_work", label: "Work" },
        ]);
    });
    it("filters each exact instance with its own capability result", () => {
        const candidates = buildThreadImportCandidates([
            {
                instanceId: "arkos",
                provider: "arkos",
                driver: "arkos",
                label: "Codex",
                enabled: true,
                isDefault: true,
                supported: true,
            },
            {
                instanceId: "codex_work",
                provider: "arkos",
                driver: "arkos",
                label: "Work",
                enabled: true,
                isDefault: false,
                supported: true,
            },
        ]);
        expect(filterThreadImportTargetsByCapabilities(candidates, [
            {
                provider: "arkos",
                supportsSkillMentions: true,
                supportsSkillDiscovery: true,
                supportsNativeSlashCommandDiscovery: true,
                supportsPluginMentions: true,
                supportsPluginDiscovery: true,
                supportsRuntimeModelList: true,
                supportsThreadImport: false,
            },
            {
                provider: "arkos",
                supportsSkillMentions: true,
                supportsSkillDiscovery: true,
                supportsNativeSlashCommandDiscovery: true,
                supportsPluginMentions: true,
                supportsPluginDiscovery: true,
                supportsRuntimeModelList: true,
                supportsThreadImport: true,
            },
        ])).toEqual([{ provider: "arkos", instanceId: "codex_work", label: "Work" }]);
    });
});
