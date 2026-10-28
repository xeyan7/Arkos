import type { ProviderKind } from "./orchestration";
import type { ModelSlug } from "./model";
export interface AgentAliasDefinition {readonly provider:ProviderKind;readonly kind:"model";
 readonly model:ModelSlug;readonly displayName:string;readonly color:"violet"|"fuchsia"|"teal"|"cyan"|"amber"|"orange";}
export type ResolvedAgentAlias=AgentAliasDefinition&{readonly alias:string};
export const AGENT_MENTION_ALIASES:Record<string,AgentAliasDefinition>={};
export const AGENT_MENTION_ALIASES_BY_PROVIDER:Record<ProviderKind,Record<string,AgentAliasDefinition>>={arkos:{}};
export function getAgentMentionAliases(_provider?:ProviderKind):ResolvedAgentAlias[]{return [];}
export function getAgentMentionAutocompleteAliases(_provider:ProviderKind):ResolvedAgentAlias[]{return [];}
export function resolveAgentAlias(_alias:string,_provider?:ProviderKind):AgentAliasDefinition|null{return null;}
export function isValidAgentAlias(_alias:string,_provider?:ProviderKind):boolean{return false;}
export function getAgentAliasNames(_provider?:ProviderKind):string[]{return [];}
