import { DEFAULT_MODEL, MODEL_OPTIONS_BY_PROVIDER, ENGINE_MODEL_CAPABILITIES, type ModelCapabilities, type ModelSelection, type ModelSlug, type ProviderKind, type ProviderOptionDescriptor, type ProviderOptionSelections } from "@arkos/contracts";
export interface SelectableModelOption { readonly slug:string; readonly name:string; readonly description?:string; }
export const EMPTY_MODEL_CAPABILITIES = ENGINE_MODEL_CAPABILITIES;
export function getModelOptions(_provider:ProviderKind="arkos") {return MODEL_OPTIONS_BY_PROVIDER.arkos;}
export function getDefaultModel(_provider:ProviderKind="arkos"):ModelSlug {return DEFAULT_MODEL;}
export function humanizeModelSlug(slug:string):string {
 return slug===DEFAULT_MODEL ? "Engine configuration" : slug.replace(/[-_]+/g," ").replace(/\b\w/g,c=>c.toUpperCase());
}
export function normalizeModelDisplayName(name:string):string {return name.trim();}
export function formatModelDisplayName(model:string|null|undefined):string|undefined {
 return model?.trim() ? "Engine configuration" : undefined;
}
export function normalizeModelSlug(model:string|null|undefined,_provider:ProviderKind="arkos"):ModelSlug|null {
 return model?.trim() ? DEFAULT_MODEL : null;
}
export function resolveModelSlug(_model:string|null|undefined,_provider:ProviderKind="arkos"):ModelSlug {return DEFAULT_MODEL;}
export function resolveModelSlugForProvider(provider:ProviderKind,model:string|null|undefined):ModelSlug {return resolveModelSlug(model,provider);}
export function resolveSelectableModel(_provider:ProviderKind,_value:string|null|undefined,_options:ReadonlyArray<SelectableModelOption>):ModelSlug {return DEFAULT_MODEL;}
export function getModelCapabilities(_provider:ProviderKind,_model:string|null|undefined):ModelCapabilities {return ENGINE_MODEL_CAPABILITIES;}
export function resolveApiModelId(selection:ModelSelection):string {return selection.model;}
export function trimOrNull<T extends string>(value:T|null|undefined):T|null {return typeof value==="string"?(value.trim() as T)||null:null;}
export function hasEffortLevel(caps:ModelCapabilities,value:string):boolean {return caps.reasoningEffortLevels.some(x=>x.value===value);}
export function getDefaultEffort(caps:ModelCapabilities):string|null {return caps.reasoningEffortLevels.find(x=>x.isDefault)?.value??null;}
export function hasContextWindowOption(caps:ModelCapabilities,value:string):boolean {return caps.contextWindowOptions.some(x=>x.value===value);}
export function getDefaultContextWindow(caps:ModelCapabilities):string|null {return caps.contextWindowOptions.find(x=>x.isDefault)?.value??null;}
export function hasAutoCompactWindowOption(caps:ModelCapabilities,value:string):boolean {return caps.autoCompactWindowOptions?.some(x=>x.value===value)??false;}
export function getDefaultAutoCompactWindow(caps:ModelCapabilities):string|null {return caps.autoCompactWindowOptions?.find(x=>x.isDefault)?.value??null;}
export function resolveLabeledOptionValue(options:ReadonlyArray<{value:string;isDefault?:boolean|undefined}>|undefined,value:string|null|undefined):string|null {
 return options?.find(x=>x.value===value)?.value??options?.find(x=>x.isDefault)?.value??null;
}
type OptionInput = ProviderOptionSelections | Readonly<Record<string,unknown>> | null | undefined;
function selected(input:OptionInput,id:string):unknown {
 return Array.isArray(input)?input.find(x=>x.id===id)?.value:(input as Readonly<Record<string,unknown>>|null|undefined)?.[id];
}
export function getProviderOptionBooleanSelectionValue(input:OptionInput,id:string):boolean|undefined {
 const value=selected(input,id);return typeof value==="boolean"?value:undefined;
}
export function getModelSelectionStringOptionValue(selection:ModelSelection|null|undefined,id:string):string|null {
 const value=selected(selection?.options,id);return typeof value==="string"?trimOrNull(value):null;
}
export function getModelSelectionBooleanOptionValue(selection:ModelSelection|null|undefined,id:string):boolean|undefined {
 return getProviderOptionBooleanSelectionValue(selection?.options,id);
}
export function getProviderOptionDescriptors(input:{provider:ProviderKind;caps:ModelCapabilities;selections?:OptionInput}):ReadonlyArray<ProviderOptionDescriptor> {
 return input.caps.optionDescriptors??[];
}
export function getProviderOptionCurrentValue(descriptor:ProviderOptionDescriptor|null|undefined):string|boolean|undefined {
 if(!descriptor)return undefined;return descriptor.type==="boolean"?descriptor.currentValue:descriptor.currentValue??descriptor.options.find(x=>x.isDefault)?.id;
}
