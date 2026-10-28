import type {ProviderInstanceId,ProviderKind,ProviderStartOptions,ServerProviderStatus} from "@arkos/contracts";
const statuses:ServerProviderStatus[]=[];
export function useChatProviderStatus(_input:unknown){return {providerStatuses:statuses,
 rememberCustomBinaryPathForDispatch:(_input:{threadId:string;provider:ProviderKind;providerInstanceId:ProviderInstanceId;providerOptions:ProviderStartOptions|undefined})=>{},};}
