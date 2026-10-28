import type { ProviderKind, ProviderInstanceId, ServerProviderStatus } from "@arkos/contracts";
import type {ProviderModelOption} from "../../providerModelOptions";
export interface ProviderModelPickerInstance {
    readonly instanceId: ProviderInstanceId;
    readonly provider: ProviderKind;
    readonly label: string;
    readonly accentColor?: string | undefined;
    readonly enabled: boolean;
    readonly isDefault: boolean;
}
export type ProviderModelOptionsByProviderInstance = Partial<Record<ProviderInstanceId, ReadonlyArray<ProviderModelOption>>>;
export function findProviderStatusForInstance(input: {
    providers: ReadonlyArray<ServerProviderStatus> | undefined;
    provider: ProviderKind;
    instanceId: ProviderInstanceId;
}): ServerProviderStatus | undefined {
    return input.providers?.find((entry) => (entry.driver ?? entry.provider) === input.provider &&
        (entry.instanceId ?? entry.provider) === input.instanceId);
}
export const AVAILABLE_PROVIDER_OPTIONS:ReadonlyArray<{value:ProviderKind;label:string;available:boolean}>=[];
export function resolveVisibleProviderOptions(_input:unknown):typeof AVAILABLE_PROVIDER_OPTIONS{return [];}
export function resolveLiveProviderAvailability(_status:ServerProviderStatus|undefined):{disabled:boolean;label:string|null}{return {disabled:true,label:"Unavailable"};}
export function resolveProviderModelLabel(_input:unknown):string{return "No runtime connected";}
export function getProviderIconClassName(_provider:ProviderKind,_fallback="text-muted-foreground/70"):string{return _fallback;}
