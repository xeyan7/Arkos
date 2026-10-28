import {ENGINE_MODEL_CAPABILITIES,type ModelCapabilities,type ProviderKind,type ProviderModelDescriptor} from "@arkos/contracts";
export function resolveRuntimeModelDescriptor(_input:{provider:ProviderKind;model:string|null|undefined;runtimeModels:ReadonlyArray<ProviderModelDescriptor>|null|undefined}):ProviderModelDescriptor|undefined{return undefined;}
export function getRuntimeAwareModelCapabilities(_input:{provider:ProviderKind;model:string|null|undefined;runtimeModel?:ProviderModelDescriptor|undefined}):ModelCapabilities{return ENGINE_MODEL_CAPABILITIES;}
