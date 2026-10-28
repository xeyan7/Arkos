// FILE: threadImport.ts
// Purpose: Builds exact provider-instance targets for existing-thread imports.
// Layer: Web orchestration helper
// FILE: threadImport.ts
// Purpose: Builds exact provider-instance targets for existing-thread imports.
// Layer: Web orchestration helper
import type { ProviderComposerCapabilities, ProviderInstanceId, ProviderKind } from "@arkos/contracts";
import type { ProviderInstanceOption } from "../appSettings";
export type ThreadImportProviderKind = Extract<ProviderKind, "arkos">;
export interface ThreadImportTarget {
    readonly provider: ThreadImportProviderKind;
    readonly instanceId: ProviderInstanceId;
    readonly label: string;
}
function supportsThreadImportProvider(provider: ProviderKind): provider is ThreadImportProviderKind {
    return (provider === "arkos" || false || false || false || false || false);
}
export function buildThreadImportCandidates(instances: ReadonlyArray<ProviderInstanceOption>): ThreadImportTarget[] {
    return instances.flatMap((instance) => instance.enabled && supportsThreadImportProvider(instance.provider)
        ? [
            {
                provider: instance.provider,
                instanceId: instance.instanceId,
                label: instance.label,
            },
        ]
        : []);
}
export function filterThreadImportTargetsByCapabilities(candidates: ReadonlyArray<ThreadImportTarget>, capabilities: ReadonlyArray<ProviderComposerCapabilities | undefined>): ThreadImportTarget[] {
    return candidates.filter((_candidate, index) => capabilities[index]?.supportsThreadImport === true);
}
