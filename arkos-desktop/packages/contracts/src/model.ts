import { Schema } from "effect";
import { TrimmedNonEmptyString } from "./baseSchemas";
import type { ProviderKind } from "./orchestration";
export const ProviderOptionChoice = Schema.Struct({
  id: TrimmedNonEmptyString,
  label: TrimmedNonEmptyString,
  description: Schema.optional(TrimmedNonEmptyString),
  isDefault: Schema.optional(Schema.Literal(true)),
});
export type ProviderOptionChoice = typeof ProviderOptionChoice.Type;

const ProviderOptionDescriptorBase = {
  id: TrimmedNonEmptyString,
  label: TrimmedNonEmptyString,
  description: Schema.optional(TrimmedNonEmptyString),
} as const;

export const SelectProviderOptionDescriptor = Schema.Struct({
  ...ProviderOptionDescriptorBase,
  type: Schema.Literal("select"),
  options: Schema.Array(ProviderOptionChoice),
  currentValue: Schema.optional(TrimmedNonEmptyString),
  promptInjectedValues: Schema.optional(Schema.Array(TrimmedNonEmptyString)),
});
export type SelectProviderOptionDescriptor = typeof SelectProviderOptionDescriptor.Type;

export const BooleanProviderOptionDescriptor = Schema.Struct({
  ...ProviderOptionDescriptorBase,
  type: Schema.Literal("boolean"),
  currentValue: Schema.optional(Schema.Boolean),
});
export type BooleanProviderOptionDescriptor = typeof BooleanProviderOptionDescriptor.Type;

export const ProviderOptionDescriptor = Schema.Union([
  SelectProviderOptionDescriptor,
  BooleanProviderOptionDescriptor,
]);
export type ProviderOptionDescriptor = typeof ProviderOptionDescriptor.Type;

export const ProviderOptionSelection = Schema.Struct({
  id: TrimmedNonEmptyString,
  value: Schema.Union([TrimmedNonEmptyString, Schema.Boolean]),
});
export type ProviderOptionSelection = typeof ProviderOptionSelection.Type;

export const ProviderOptionSelections = Schema.Array(ProviderOptionSelection);
export type ProviderOptionSelections = typeof ProviderOptionSelections.Type;


/** Model choice and reasoning are owned by the configured Arkos engine. */
export const EngineModelOptions = Schema.Struct({});
export type EngineModelOptions = typeof EngineModelOptions.Type;
export type ProviderReasoningEffort = string;
export const ProviderModelOptions = Schema.Struct({ arkos: Schema.optional(EngineModelOptions) });
export type ProviderModelOptions = typeof ProviderModelOptions.Type;
export type ReasoningControlSource = "api-effort" | "provider-setting" | "prompt-prefix";

type EffortOptionBase = {
  readonly value: string;
  readonly label: string;
  readonly description?: string;
  readonly isDefault?: true;
};

export type EffortOption =
  | (EffortOptionBase & {
      readonly controlSource?: "api-effort";
      readonly apiEffortValue?: never;
    })
  | (EffortOptionBase & {
      readonly controlSource: "provider-setting";
      readonly apiEffortValue: string;
    })
  | (EffortOptionBase & {
      readonly controlSource: "prompt-prefix";
      readonly apiEffortValue?: never;
    });

export type ContextWindowOption = {
  readonly value: string;
  readonly label: string;
  readonly isDefault?: true;
};

export type ModelCapabilities = {
  readonly optionDescriptors?: readonly ProviderOptionDescriptor[];
  readonly reasoningEffortLevels: readonly EffortOption[];
  readonly supportsFastMode: boolean;
  readonly supportsThinkingToggle: boolean;
  readonly promptInjectedEffortLevels: readonly string[];
  readonly contextWindowOptions: readonly ContextWindowOption[];
  readonly autoCompactWindowOptions?: readonly ContextWindowOption[];
  readonly contextWindowTokens?: number;
  readonly variantOptions?: readonly EffortOption[];
  readonly agentOptions?: readonly EffortOption[];
};


export type ModelSlug = string;
export type ProviderWithDefaultModel = ProviderKind;
export const ENGINE_DEFAULT_MODEL = "engine-default";
export const ENGINE_MODEL_CAPABILITIES: ModelCapabilities = {
 reasoningEffortLevels: [], supportsFastMode: false, supportsThinkingToggle: false,
 promptInjectedEffortLevels: [], contextWindowOptions: [],
};
export const MODEL_OPTIONS_BY_PROVIDER = {
 arkos: [{slug: ENGINE_DEFAULT_MODEL, name: "Engine configuration", capabilities: ENGINE_MODEL_CAPABILITIES}],
};
export type ModelOptionsByProvider = typeof MODEL_OPTIONS_BY_PROVIDER;
export const DEFAULT_MODEL_BY_PROVIDER: Record<ProviderKind, ModelSlug> = {arkos: ENGINE_DEFAULT_MODEL};
export const DEFAULT_MODEL = ENGINE_DEFAULT_MODEL;
export const DEFAULT_GIT_TEXT_GENERATION_MODEL = ENGINE_DEFAULT_MODEL;
export const DEFAULT_GIT_TEXT_GENERATION_REASONING_EFFORT = "high";
export const GIT_TEXT_GENERATION_PROVIDERS = ["arkos"] as const;
export type GitTextGenerationProvider = ProviderKind;
export const MODEL_SLUG_ALIASES_BY_PROVIDER: Record<ProviderKind, Record<string,string>> = {arkos:{}};
export const MODEL_CAPABILITIES_INDEX = {arkos: {[ENGINE_DEFAULT_MODEL]: ENGINE_MODEL_CAPABILITIES}};
export const PROVIDER_DISPLAY_NAMES: Record<ProviderKind,string> = {arkos:"Arkos Engine"};
export { AGENT_MENTION_ALIASES, getAgentMentionAutocompleteAliases, getAgentMentionAliases,
 resolveAgentAlias, isValidAgentAlias, getAgentAliasNames,
 type AgentAliasDefinition, type ResolvedAgentAlias } from "./agentMentions";
