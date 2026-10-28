/** Retain saved conversation content without retaining a removed agent configuration. */
import {DEFAULT_MODEL,type ServerSettings} from "@arkos/contracts";
export function normalizeLegacyModelSelection(_input:{readonly provider:unknown;readonly instanceId?:unknown;readonly model:string;readonly options:unknown}):Record<string,unknown>{return {provider:"arkos",instanceId:"arkos",model:DEFAULT_MODEL};}
export function normalizePersistedModelSelection(input:unknown,_settings?:ServerSettings):unknown{return input&&typeof input==="object"&&!Array.isArray(input)?{provider:"arkos",instanceId:"arkos",model:DEFAULT_MODEL}:input;}
