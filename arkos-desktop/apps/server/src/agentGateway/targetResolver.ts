import type {ModelSelection,ProviderKind,ProviderModelDescriptor,ServerProviderAuthStatus} from "@arkos/contracts";
import {Effect} from "effect";
import type {ProviderDiscoveryServiceShape} from "../provider/Services/ProviderDiscoveryService";
export type AgentGatewayTargetErrorCode = "provider_unavailable" | "model_unavailable" | "model_option_unavailable";
export class AgentGatewayTargetError extends Error {
    readonly code: AgentGatewayTargetErrorCode;
    readonly details?: unknown;
    constructor(code: AgentGatewayTargetErrorCode, message: string, details?: unknown) {
        super(message);
        this.name = "AgentGatewayTargetError";
        this.code = code;
        this.details = details;
    }
}
export interface AgentGatewayProviderCatalog {
    readonly provider: ProviderKind;
    readonly defaultModel: string | null;
    readonly models: ReadonlyArray<ProviderModelDescriptor>;
    readonly enabled: boolean;
    readonly available: boolean;
    readonly authStatus?: ServerProviderAuthStatus;
    readonly source?: string;
    readonly error?: string;
}
export interface AgentGatewayProviderAvailability {
    readonly enabled: boolean;
    /** Undefined means health has not produced a trustworthy snapshot yet. */
    readonly available?: boolean;
    readonly authStatus?: ServerProviderAuthStatus;
    readonly message?: string;
}
export type AgentGatewayTargetOptionValue = string | number | boolean;
export interface AgentGatewayTargetOptionRule {
    readonly key: string;
    readonly valueType: "string" | "number" | "boolean";
    readonly allowedValues: ReadonlyArray<AgentGatewayTargetOptionValue>;
    readonly allowedValuesSource: "provider-contract" | "model-discovery";
    readonly allowsCustomValue?: boolean;
}
export interface AgentGatewayTargetOptionGuidance {
    readonly primaryOptionKey: string;
    readonly alternativeOptionKeys: ReadonlyArray<string>;
    readonly optionSelectionRule: string;
    readonly providerOptions: ReadonlyArray<AgentGatewayTargetOptionRule>;
    readonly optionsByModel: Readonly<Record<string, ReadonlyArray<AgentGatewayTargetOptionRule>>>;
    readonly exampleTarget: {
        readonly provider: ProviderKind;
        readonly instanceId: string;
        readonly model: string;
        readonly options: Readonly<Record<string, AgentGatewayTargetOptionValue>>;
    } | null;
}
export const AGENT_GATEWAY_TARGET_OPTIONS_DESCRIPTION="No agent runtime is connected.";
export function loadAgentGatewayProviderCatalog(input:{provider:ProviderKind;discovery:ProviderDiscoveryServiceShape;availability?:AgentGatewayProviderAvailability;cwd?:string}):Effect.Effect<AgentGatewayProviderCatalog>{return Effect.succeed({provider:input.provider,defaultModel:null,models:[],enabled:false,available:false,source:"unavailable",error:"No agent runtime is connected."});}
export function agentGatewayTargetOptionGuidance(_catalog:AgentGatewayProviderCatalog):AgentGatewayTargetOptionGuidance{return {primaryOptionKey:"",alternativeOptionKeys:[],optionSelectionRule:AGENT_GATEWAY_TARGET_OPTIONS_DESCRIPTION,providerOptions:[],optionsByModel:{},exampleTarget:null};}
export function resolveAgentGatewayTarget(_input:{target:ModelSelection;discovery:ProviderDiscoveryServiceShape;availability?:AgentGatewayProviderAvailability;cwd?:string}):Effect.Effect<ModelSelection,AgentGatewayTargetError>{return Effect.fail(new AgentGatewayTargetError("provider_unavailable","No agent runtime is connected."));}
