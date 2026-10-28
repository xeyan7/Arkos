import type {ProviderKind,ServerProviderUsageSnapshot} from "@arkos/contracts";
export const PROVIDER_USAGE_PROVIDERS:ReadonlyArray<ProviderKind>=[];
export function providerUsageLabel(_provider:string|null|undefined):string{return "Usage";}
export function providerUsageDisplayName(_provider:string|null|undefined):string{return "Arkos";}
export function providerUsageLearnMoreHref(_provider:string|null|undefined):string|null{return null;}
export function providerUsageNeedsAuthDetail(_provider:string|null|undefined):string{return "No agent runtime is connected.";}
export function selectVisibleProviderUsageSnapshots(_snapshots:ReadonlyArray<ServerProviderUsageSnapshot>):ReadonlyArray<ServerProviderUsageSnapshot>{return [];}
