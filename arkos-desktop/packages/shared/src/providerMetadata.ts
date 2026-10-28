import type { ProviderKind } from "@arkos/contracts";
export interface ProviderDescriptor {
 readonly kind: ProviderKind; readonly displayName: string; readonly available: boolean;
 readonly supportsNativeTurnSteering: boolean; readonly setupDocsHref: string | null;
 readonly usage: {readonly signInCommand:string;readonly learnMoreHref:string} | null;
}
export const PROVIDER_DESCRIPTORS = [{kind:"arkos", displayName:"Arkos Engine", available:true,
 supportsNativeTurnSteering:false, setupDocsHref:null, usage:null}] as const satisfies readonly ProviderDescriptor[];
export const PROVIDER_DESCRIPTOR_BY_KIND = {arkos:PROVIDER_DESCRIPTORS[0]};
export const providerSupportsNativeTurnSteering = (_kind:string):boolean => false;
