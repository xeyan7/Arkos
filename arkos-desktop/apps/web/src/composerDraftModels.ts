// FILE: composerDraftModels.ts
// Purpose: Normalizes provider-scoped model selections and resolves effective composer models.
// Exports: Model state helpers used by persistence, actions, and the public facade.
// FILE: composerDraftModels.ts
// Purpose: Normalizes provider-scoped model selections and resolves effective composer models.
// Exports: Model state helpers used by persistence, actions, and the public facade.
// FILE: composerDraftModels.ts
// Purpose: Normalizes provider-scoped model selections and resolves effective composer models.
// Exports: Model state helpers used by persistence, actions, and the public facade.
// FILE: composerDraftModels.ts
// Purpose: Normalizes provider-scoped model selections and resolves effective composer models.
// Exports: Model state helpers used by persistence, actions, and the public facade.
import { ProviderInstanceId, ProviderKind, type ModelSelection, type ModelSlug, type ProviderModelOptions } from "@arkos/contracts";
import * as Schema from "effect/Schema";
import { getDefaultModel, normalizeModelSlug, resolveModelSlugForProvider, resolveSelectableModel } from "@arkos/shared/model";
import { resolveAppModelSelection } from "./appSettings";
import type { ComposerThreadDraftState, ModelSelectionByProviderInstance } from "./composerDraftDomain";

export const COMPOSER_PROVIDER_KINDS = [
    "arkos"
] as const satisfies readonly ProviderKind[];
const isProviderKind = Schema.is(ProviderKind);
const isProviderInstanceId = Schema.is(ProviderInstanceId);
export const LegacyCodexFields = Schema.Struct({
    effort: Schema.optionalKey(Schema.String),
    serviceTier: Schema.optionalKey(Schema.String),
});
export type LegacyCodexFields = typeof LegacyCodexFields.Type;
export interface EffectiveComposerModelState {
    selectedModel: ModelSlug;
    modelOptions: ProviderModelOptions | null;
}
function mergeProviderModelOptionsFromSelections(...selections: ReadonlyArray<ModelSelection | null | undefined>): ProviderModelOptions | null {
    const result: Partial<Record<ProviderKind, ProviderModelOptions[ProviderKind]>> = {};
    for (const selection of selections) {
        if (!selection)
            continue;
        if (selection.options) {
            result[selection.provider] = selection.options;
        }
        else {
            delete result[selection.provider];
        }
    }
    return Object.keys(result).length > 0 ? (result as ProviderModelOptions) : null;
}
function modelSelectionMatchesProviderInstance(selection: ModelSelection | null | undefined, provider: ProviderKind, instanceId: ProviderInstanceId | null | undefined): selection is ModelSelection {
    if (!selection || selection.provider !== provider) {
        return false;
    }
    return (selection.instanceId ?? selection.provider) === (instanceId ?? provider);
}
function deriveEffectiveComposerModelOptions(input: {
    draft: Pick<ComposerThreadDraftState, "modelSelectionByProvider" | "activeProvider"> | null | undefined;
    selectedProvider: ProviderKind;
    selectedProviderInstanceId?: ProviderInstanceId | null | undefined;
    threadModelSelection: ModelSelection | null | undefined;
    projectModelSelection: ModelSelection | null | undefined;
}): ProviderModelOptions | null {
    const selectionForTarget = (selection: ModelSelection | null | undefined) => selection?.provider !== input.selectedProvider ||
        modelSelectionMatchesProviderInstance(selection, input.selectedProvider, input.selectedProviderInstanceId)
        ? selection
        : null;
    const baseOptions = mergeProviderModelOptionsFromSelections(selectionForTarget(input.projectModelSelection), selectionForTarget(input.threadModelSelection));
    const draftSelections = input.draft?.modelSelectionByProvider;
    if (!draftSelections) {
        return baseOptions;
    }
    const result: Partial<Record<ProviderKind, ProviderModelOptions[ProviderKind]>> = baseOptions
        ? { ...baseOptions }
        : {};
    for (const selection of Object.values(draftSelections)) {
        if (!selection)
            continue;
        const provider = selection.provider;
        if (provider === input.selectedProvider &&
            !modelSelectionMatchesProviderInstance(selection, input.selectedProvider, input.selectedProviderInstanceId)) {
            continue;
        }
        if (selection.options) {
            result[provider] = selection.options;
        }
        else {
            delete result[provider];
        }
    }
    return Object.keys(result).length > 0 ? (result as ProviderModelOptions) : null;
}
export function normalizeProviderKind(value: unknown): ProviderKind | null { return typeof value === "string" ? "arkos" : null; }
function trimStringOrUndefined(value: unknown): string | undefined {
    if (typeof value !== "string") {
        return undefined;
    }
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : undefined;
}
export function normalizeProviderInstanceId(value: unknown): ProviderInstanceId | undefined {
    const trimmed = trimStringOrUndefined(value);
    return trimmed !== undefined && isProviderInstanceId(trimmed) ? trimmed : undefined;
}
export function providerInstanceModelSelectionKey(provider: ProviderKind, instanceId?: ProviderInstanceId | null | undefined): ProviderInstanceId {
    return normalizeProviderInstanceId(instanceId) ?? (provider as ProviderInstanceId);
}
export function modelSelectionStorageKey(selection: ModelSelection): ProviderInstanceId {
    return providerInstanceModelSelectionKey(selection.provider, selection.instanceId);
}
export function readModelSelectionForProviderInstance(selections: ModelSelectionByProviderInstance | null | undefined, provider: ProviderKind, instanceId?: ProviderInstanceId | null | undefined): ModelSelection | undefined {
    return selections?.[providerInstanceModelSelectionKey(provider, instanceId)];
}
export function normalizeModelSelectionMapByInstance(selections: ModelSelectionByProviderInstance): ModelSelectionByProviderInstance {
    const result: ModelSelectionByProviderInstance = {};
    for (const selection of Object.values(selections)) {
        if (selection) {
            result[modelSelectionStorageKey(selection)] = selection;
        }
    }
    return result;
}
function booleanOrUndefined(value: unknown): boolean | undefined {
    return typeof value === "boolean" ? value : undefined;
}
export function makeModelSelection(_provider: ProviderKind, _model: string, _options?: ProviderModelOptions[ProviderKind], _supportsAutoMode?: boolean, _instanceId?: ProviderInstanceId | null): ModelSelection { return { provider: "arkos", instanceId: "arkos", model: "engine-default" }; }
export function normalizeProviderModelOptions(_value: unknown, _provider?: ProviderKind | null, _legacy?: LegacyCodexFields): ProviderModelOptions | null { return null; }
export function normalizeModelSelection(value: unknown, _legacy?: unknown): ModelSelection | null { return value && typeof value === "object" ? makeModelSelection("arkos", "engine-default") : null; }
export function reconcileProviderScopedModelSelection(requested: ModelSelection, current: ModelSelection | null | undefined): ModelSelection { return requested; }
export function stripNonStickyModelOptions(_selection: ModelSelection): ModelSelection { return makeModelSelection("arkos", "engine-default"); }
export function sanitizeStickyModelSelectionMap(map: ModelSelectionByProviderInstance): ModelSelectionByProviderInstance {
    let next = map;
    for (const [key, selection] of Object.entries(map)) {
        ;
    }
    return next;
}
export function legacySyncModelSelectionOptions(selection: ModelSelection | null, _options: ProviderModelOptions | null | undefined): ModelSelection | null { return selection; }
export function legacyMergeModelSelectionIntoProviderModelOptions(_selection: ModelSelection | null, _current: ProviderModelOptions | null | undefined): ProviderModelOptions | null { return null; }
function legacyReplaceProviderModelOptions(currentModelOptions: ProviderModelOptions | null | undefined, provider: ProviderKind, nextProviderOptions: ProviderModelOptions[ProviderKind] | null | undefined): ProviderModelOptions | null {
    const { [provider]: _discardedProviderModelOptions, ...otherProviderModelOptions } = currentModelOptions ?? {};
    const normalizedNextProviderOptions = normalizeProviderModelOptions({ [provider]: nextProviderOptions }, provider);
    return normalizeProviderModelOptions({
        ...otherProviderModelOptions,
        ...(normalizedNextProviderOptions ? normalizedNextProviderOptions : {}),
    });
}
export function legacyToModelSelectionByProvider(modelSelection: ModelSelection | null, modelOptions: ProviderModelOptions | null | undefined): ModelSelectionByProviderInstance {
    const result: ModelSelectionByProviderInstance = {};
    // Add entries from the options bag (for non-active providers)
    if (modelOptions) {
        for (const provider of COMPOSER_PROVIDER_KINDS) {
            const options = modelOptions[provider];
            if (options && Object.keys(options).length > 0) {
                const model = modelSelection?.provider === provider ? modelSelection.model : getDefaultModel(provider);
                if (model) {
                    result[providerInstanceModelSelectionKey(provider)] = makeModelSelection(provider, model, options);
                }
            }
        }
    }
    // Add/overwrite the active selection (it's authoritative for its provider)
    if (modelSelection) {
        result[modelSelectionStorageKey(modelSelection)] = modelSelection;
    }
    return result;
}
export function deriveEffectiveComposerModelState(input: {
    draft: Pick<ComposerThreadDraftState, "modelSelectionByProvider" | "activeProvider"> | null | undefined;
    selectedProvider: ProviderKind;
    selectedProviderInstanceId?: ProviderInstanceId | null | undefined;
    threadModelSelection: ModelSelection | null | undefined;
    projectModelSelection: ModelSelection | null | undefined;
    customModelsByProvider: Record<ProviderKind, readonly string[]>;
    availableModelOptionsByProvider?: Partial<Record<ProviderKind, ReadonlyArray<{
        slug: string;
        name: string;
    }>>>;
}): EffectiveComposerModelState {
    const selectionMatchesSelectedInstance = (selection: ModelSelection | null | undefined): selection is ModelSelection => modelSelectionMatchesProviderInstance(selection, input.selectedProvider, input.selectedProviderInstanceId);
    const resolveAvailableModel = (candidate: string | null | undefined): ModelSlug | null => {
        const availableOptions = input.availableModelOptionsByProvider?.[input.selectedProvider];
        if (!availableOptions || availableOptions.length === 0) {
            return null;
        }
        return resolveSelectableModel(input.selectedProvider, candidate, availableOptions);
    };
    const baseModel = resolveModelSlugForProvider(input.selectedProvider, (selectionMatchesSelectedInstance(input.threadModelSelection)
        ? input.threadModelSelection.model
        : null) ??
        (selectionMatchesSelectedInstance(input.projectModelSelection)
            ? input.projectModelSelection.model
            : null) ??
        getDefaultModel(input.selectedProvider));
    const persistedThreadModel = selectionMatchesSelectedInstance(input.threadModelSelection)
        ? (normalizeModelSlug(input.threadModelSelection.model, input.selectedProvider) ??
            input.threadModelSelection.model)
        : null;
    const persistedProjectModel = selectionMatchesSelectedInstance(input.projectModelSelection)
        ? (normalizeModelSlug(input.projectModelSelection.model, input.selectedProvider) ??
            input.projectModelSelection.model)
        : null;
    const activeSelection = readModelSelectionForProviderInstance(input.draft?.modelSelectionByProvider, input.selectedProvider, input.selectedProviderInstanceId);
    const selectedDraftModel = activeSelection?.model
        ? resolveAppModelSelection(input.selectedProvider, input.customModelsByProvider, activeSelection.model)
        : null;
    // pi and omp serve fully dynamic catalogs, so a draft model can be absent
    // from the option list; keep it ahead of the first-catalog-entry fallback.
    const unlistedDraftModel = null;
    const selectedModel = resolveAvailableModel(activeSelection?.model) ??
        resolveAvailableModel(selectionMatchesSelectedInstance(input.threadModelSelection)
            ? input.threadModelSelection.model
            : null) ??
        resolveAvailableModel(selectionMatchesSelectedInstance(input.projectModelSelection)
            ? input.projectModelSelection.model
            : null) ??
        resolveAvailableModel(selectedDraftModel) ??
        persistedThreadModel ??
        persistedProjectModel ??
        unlistedDraftModel ??
        input.availableModelOptionsByProvider?.[input.selectedProvider]?.[0]?.slug ??
        selectedDraftModel ??
        baseModel ??
        getDefaultModel("arkos");
    const modelOptions = deriveEffectiveComposerModelOptions(input);
    return {
        selectedModel,
        modelOptions,
    };
}
export function resolvePreferredComposerModelSelection(input: {
    draft: Pick<ComposerThreadDraftState, "modelSelectionByProvider" | "activeProvider"> | null | undefined;
    threadModelSelection: ModelSelection | null | undefined;
    projectModelSelection: ModelSelection | null | undefined;
    defaultProvider?: ProviderKind | null | undefined;
    resolveProviderForInstanceId?: (instanceId: ProviderInstanceId) => ProviderKind | null | undefined;
}): ModelSelection {
    // The draft's selection is the user's most recently used target: a fresh draft
    // is seeded from the sticky (last-used) state, so this precedence is what
    // makes a new chat reopen with the model and options used last time. Project
    // and global defaults only apply when nothing has been used yet.
    const activeInstanceId = input.draft?.activeProvider ?? null;
    const activeDraftSelection = activeInstanceId
        ? input.draft?.modelSelectionByProvider[activeInstanceId]
        : undefined;
    const draftProviderWithSelection = activeDraftSelection?.provider ?? null;
    const activeInstanceProvider = activeInstanceId
        ? (activeDraftSelection?.provider ??
            input.resolveProviderForInstanceId?.(activeInstanceId) ??
            normalizeProviderKind(activeInstanceId))
        : null;
    const preferredProvider = activeInstanceProvider ??
        draftProviderWithSelection ??
        input.threadModelSelection?.provider ??
        input.projectModelSelection?.provider ??
        input.defaultProvider ?? "arkos";
    const preferredPersistedSelection = input.threadModelSelection?.provider === preferredProvider
        ? input.threadModelSelection
        : input.projectModelSelection?.provider === preferredProvider
            ? input.projectModelSelection
            : null;
    const preferredInstanceId = providerInstanceModelSelectionKey(preferredProvider, activeInstanceProvider === preferredProvider
        ? activeInstanceId
        : preferredPersistedSelection?.instanceId);
    const persistedSelection = (modelSelectionMatchesProviderInstance(input.threadModelSelection, preferredProvider, preferredInstanceId)
        ? input.threadModelSelection
        : null) ??
        (modelSelectionMatchesProviderInstance(input.projectModelSelection, preferredProvider, preferredInstanceId)
            ? input.projectModelSelection
            : null);
    const draftSelection = readModelSelectionForProviderInstance(input.draft?.modelSelectionByProvider, preferredProvider, preferredInstanceId);
    // Pi and OMP have no static default model, so an empty draft falls back to Codex.
    const fallbackProvider = preferredProvider;
    const fallbackInstanceId = fallbackProvider === preferredProvider ? preferredInstanceId : fallbackProvider;
    return (draftSelection ??
        persistedSelection ??
        makeModelSelection(fallbackProvider, getDefaultModel(fallbackProvider), undefined, undefined, fallbackInstanceId));
}
