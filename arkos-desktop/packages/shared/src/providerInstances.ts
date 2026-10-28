import type { ModelSelection, ProviderDriverKind, ProviderInstanceConfig, ProviderInstanceConfigMap, ProviderInstanceId, ProviderKind, ProviderStartOptions, ServerSettings } from "@arkos/contracts";
export const BUILT_IN_PROVIDER_KINDS = ["arkos"] as const;
export interface ResolvedProviderInstance {
 readonly instanceId:ProviderInstanceId;readonly driver:ProviderKind;readonly displayName:string;
 readonly enabled:boolean;readonly isDefault:boolean;readonly config:Record<string,unknown>;
 readonly environment:Readonly<Record<string,string>>;readonly raw:ProviderInstanceConfig;
}
export interface UnsupportedProviderInstance extends Omit<ResolvedProviderInstance,"driver"> {readonly driver:ProviderDriverKind;}
export function isProviderKind(value:unknown):value is ProviderKind {return value==="arkos";}
export function defaultInstanceIdForProvider(_provider:ProviderKind):ProviderInstanceId {return "arkos";}
export function unresolvedAutomationInstanceId(_provider:ProviderDriverKind):ProviderInstanceId {return "arkos";}
export function isUnresolvedAutomationInstanceId(_id:string|null|undefined):boolean {return false;}
export function providerProfileDirectoryEnvironment(_provider:ProviderKind,_dir:string):Readonly<Record<string,string>> {return {};}
export function providerImportedDirectoryConfig(_provider:ProviderKind,_dir:string):Record<string,unknown> {return {};}
export function inferLegacyProviderKindFromInstanceId(_id:string|null|undefined):ProviderKind {return "arkos";}
export function inferLegacyProviderKindFromModel(_model:string|null|undefined):ProviderKind {return "arkos";}
export function inferLegacyProviderKindFromModelSelection(_selection:unknown):ProviderKind {return "arkos";}
export function resolveModelSelectionInstanceId(_selection:Pick<ModelSelection,"provider"|"instanceId">):ProviderInstanceId {return "arkos";}
export function resolveProviderStatusInstanceId(_status:{instanceId?:string|undefined;driver?:string|undefined;provider?:string|undefined}):ProviderInstanceId {return "arkos";}
export function deriveProviderInstanceConfigMap(_settings:ServerSettings):ProviderInstanceConfigMap {return {arkos:{driver:"arkos",displayName:"Arkos Engine",enabled:true}};}
export function deriveProviderInstances(settings:ServerSettings):ReadonlyArray<ResolvedProviderInstance> {
 return [{instanceId:"arkos",driver:"arkos",displayName:"Arkos Engine",enabled:true,isDefault:true,
 config:{},environment:{},raw:deriveProviderInstanceConfigMap(settings).arkos!}];
}
export function deriveUnsupportedProviderInstances(_settings:ServerSettings):ReadonlyArray<UnsupportedProviderInstance> {return [];}
export function resolveProviderInstance(settings:ServerSettings,target:{provider?:ProviderKind|undefined;instanceId?:ProviderInstanceId|undefined}):ResolvedProviderInstance|null {
 if(target.provider!==undefined&&target.provider!=="arkos")return null;
 if(target.instanceId!==undefined&&target.instanceId!=="arkos")return null;
 return deriveProviderInstances(settings)[0]!;
}
export function providerStartOptionsFromInstance(_instance:ResolvedProviderInstance):ProviderStartOptions|undefined {return undefined;}
export function mergeProviderStartOptions(_base:ProviderStartOptions|undefined,_overlay:ProviderStartOptions|undefined):ProviderStartOptions|undefined {return undefined;}
