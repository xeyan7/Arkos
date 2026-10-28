import type { ModelSlug, ProviderKind, ProviderModelDescriptor, ProviderModelOptions } from "@arkos/contracts";
export type ComposerProviderStateInput={provider:ProviderKind;model:ModelSlug;runtimeModel?:ProviderModelDescriptor|undefined;prompt:string;modelOptions:ProviderModelOptions|null|undefined};
export type ComposerProviderState={provider:ProviderKind;promptEffort:string|null;modelOptionsForDispatch:ProviderModelOptions[ProviderKind]|undefined;composerFrameClassName?:string;composerSurfaceClassName?:string;modelPickerIconClassName?:string};
export function getComposerProviderState(_input:ComposerProviderStateInput):ComposerProviderState{return {provider:"arkos",promptEffort:null,modelOptionsForDispatch:undefined};}
