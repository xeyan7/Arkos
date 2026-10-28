import { DEFAULT_MODEL, type ModelSelection, type ProviderInstanceId, type ProviderKind, type ProviderModelOptions } from "@arkos/contracts";
import { normalizeModelDisplayName } from "@arkos/shared/model";
export type ProviderOptions=ProviderModelOptions[ProviderKind];
export interface ModelSelectionBuildMetadata {readonly instanceId?:ProviderInstanceId|null|undefined;}
export interface ProviderModelOption {slug:string;name:string;description?:string;upstreamProviderId?:string;upstreamProviderName?:string;role?:{name:string;model:string;thinkingLevel?:string};}
export interface ProviderModelOptionGroup {
    key: string;
    label: string | null;
    options: ProviderModelOption[];
}
function normalizeCatalogModelName(name: string): string {
    return normalizeModelDisplayName(name);
}
export function providerModelCostMultiplierLabel(description?: string): string | null {
    const multiplier = description?.trim().match(/^(\d+(?:\.\d+)?)x(?:\s|$)/i)?.[1];
    return multiplier ? `${multiplier}×` : null;
}
export function groupProviderModelOptions(options: ReadonlyArray<ProviderModelOption>): ProviderModelOptionGroup[] {
    const groupedOptions: ProviderModelOptionGroup[] = [];
    const groupIndexByKey = new Map<string, number>();
    for (const option of options) {
        const upstreamProviderId = option.upstreamProviderId?.trim();
        const upstreamProviderName = option.upstreamProviderName?.trim();
        const groupLabel = upstreamProviderName && upstreamProviderName.length > 0
            ? upstreamProviderName
            : upstreamProviderId && upstreamProviderId.length > 0
                ? upstreamProviderId
                : null;
        const groupKey = groupLabel
            ? `${(upstreamProviderId ?? groupLabel).trim().toLowerCase()}`
            : "__ungrouped__";
        const existingIndex = groupIndexByKey.get(groupKey);
        if (existingIndex !== undefined) {
            groupedOptions[existingIndex]!.options.push(option);
            continue;
        }
        groupIndexByKey.set(groupKey, groupedOptions.length);
        groupedOptions.push({
            key: groupKey,
            label: groupLabel,
            options: [option],
        });
    }
    return groupedOptions;
}
export function groupProviderModelOptionsWithFavorites(input: {
    options: ReadonlyArray<ProviderModelOption>;
    favoriteSlugs: ReadonlySet<string>;
    favoriteLabel?: string;
}): ProviderModelOptionGroup[] {
    if (input.favoriteSlugs.size === 0) {
        return groupProviderModelOptions(input.options);
    }
    const favoriteOptions = input.options.filter((option) => input.favoriteSlugs.has(option.slug));
    if (favoriteOptions.length === 0) {
        return groupProviderModelOptions(input.options);
    }
    const groupedOptions = groupProviderModelOptions(input.options.filter((option) => !input.favoriteSlugs.has(option.slug)));
    return [
        {
            key: "__favorites__",
            label: input.favoriteLabel ?? "Favourites",
            options: favoriteOptions,
        },
        ...groupedOptions,
    ];
}
export function shouldUseCollapsibleModelGroups(groupCount: number, isSearching: boolean): boolean {
    return groupCount >= COLLAPSIBLE_MODEL_GROUP_THRESHOLD && !isSearching;
}
export function resolveModelGroupDefaultOpen(input: {
    groupKey: string;
    options: ReadonlyArray<ProviderModelOption>;
    activeModel: string;
    groupCount: number;
}): boolean {
    if (input.groupCount < COLLAPSIBLE_MODEL_GROUP_THRESHOLD) {
        return true;
    }
    if (input.groupKey === "__favorites__") {
        return true;
    }
    return input.options.some((option) => option.slug === input.activeModel);
}
export const COLLAPSIBLE_MODEL_GROUP_THRESHOLD=3;
export function providerModelOptionProvenanceLabel(_input:{provider:ProviderKind;option:ProviderModelOption}):string{return "Arkos Engine";}
export function formatProviderModelOptionName(_input:{provider:ProviderKind;slug:string}):string{return "Engine configuration";}
export function mergeDynamicModelOptions(_input:{provider:ProviderKind;[key:string]:unknown}):ReadonlyArray<ProviderModelOption>{return [{slug:DEFAULT_MODEL,name:"Engine configuration"}];}
export function buildNextProviderOptions(_provider:ProviderKind,_options:ProviderOptions|null|undefined,_patch:Record<string,unknown>):ProviderOptions{return {};}
export function buildProviderOptionPatch(_provider:ProviderKind,_id:string,_value:string|boolean):Record<string,unknown>{return {};}
export function buildModelSelection(_provider:ProviderKind,_model:string,_options?:ProviderOptions|null,_runtimeHint?:boolean|ModelSelectionBuildMetadata,_metadata?:ModelSelectionBuildMetadata):ModelSelection {
 return {provider:"arkos",instanceId:"arkos",model:DEFAULT_MODEL};
}

export type ComposerModelSelectionOptions={modelOptions?:ProviderOptions;instanceId?:ProviderInstanceId};
