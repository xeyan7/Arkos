import type {ProviderAgentDescriptor,ProviderInstanceId,ProviderKind,ProviderModelDescriptor} from "@arkos/contracts";
import {queryOptions} from "@tanstack/react-query";
import type {getCustomModelsByProvider} from "../appSettings";
import type {ProviderModelOption} from "../providerModelOptions";
import type {ProviderModelOptionsByProviderInstance} from "../components/chat/ProviderModelPicker";
export interface ProviderModelCatalog {
    refreshModels: (provider: ProviderKind, instanceId: ProviderInstanceId, refresh: "if-stale" | "now") => Promise<void>;
    customModelsByProvider: ReturnType<typeof getCustomModelsByProvider>;
    modelOptionsByProvider: Record<ProviderKind, ReadonlyArray<ProviderModelOption & {
        isCustom?: boolean;
    }>>;
    modelOptionsByProviderInstance: ProviderModelOptionsByProviderInstance;
    /** Providers whose runtime model discovery is still pending (no usable list yet). */
    loadingModelProviders: Partial<Record<ProviderKind, boolean>>;
    /**
     * Runtime-discovered model descriptors per provider. Composer-style trait
     * controls (effort, fast mode, thinking, context window) are sourced from
     * these for cursor/codex/etc., so any surface that wants the effort picker
     * must feed them through (see {@link selectedRuntimeModel}).
     */
    runtimeModelsByProvider: Record<ProviderKind, ReadonlyArray<ProviderModelDescriptor>>;
    /** Account-local runtime descriptors; known accounts are empty until discovery resolves. */
    runtimeModelsByProviderInstance: Partial<Record<ProviderInstanceId, ReadonlyArray<ProviderModelDescriptor>>>;
    /** The runtime descriptor matching `selectedProvider` + its selected-model hint. */
    selectedRuntimeModel: ProviderModelDescriptor | undefined;
    /** Runtime-discovered agents/modes for the selected provider (opencode/claude/codex). */
    selectedRuntimeAgents: ReadonlyArray<ProviderAgentDescriptor>;
    /** Loading state used by the selected provider's bootstrap skeleton. */
    selectedProviderModelsLoading: boolean;
    /** Whether the selected provider requires and is still waiting on runtime models. */
    selectedProviderRuntimeModelDiscoveryPending: boolean;
    /** Discovery failure detail per provider (268 passthrough). */
    discoveryErrorsByProvider: Partial<Record<ProviderKind, string | undefined>>;
}
const emptyCatalog:ProviderModelCatalog={refreshModels:async()=>{},customModelsByProvider:{arkos:[]},
 modelOptionsByProvider:{arkos:[]},modelOptionsByProviderInstance:{},loadingModelProviders:{},
 runtimeModelsByProvider:{arkos:[]},runtimeModelsByProviderInstance:{},selectedRuntimeModel:undefined,
 selectedRuntimeAgents:[],selectedProviderModelsLoading:false,selectedProviderRuntimeModelDiscoveryPending:false,discoveryErrorsByProvider:{}};
export function useProviderModelCatalog(_input:unknown):ProviderModelCatalog{return emptyCatalog;}
export function modelQueryOptionsForProviderInstance(_input:unknown){return queryOptions({queryKey:["runtime-models-unavailable"],queryFn:async()=>({models:[] as ProviderModelDescriptor[],source:"unavailable",cached:false}),enabled:false});}
