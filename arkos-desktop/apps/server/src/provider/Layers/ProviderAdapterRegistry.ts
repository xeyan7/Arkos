/** Empty registry: all external agent implementations have been removed. */
import {Effect,Layer} from "effect";
import {ProviderAdapterRegistry,type ProviderAdapterRegistryShape} from "../Services/ProviderAdapterRegistry";
import {ProviderUnsupportedError} from "../Errors";
export const ProviderAdapterRegistryLive=Layer.succeed(ProviderAdapterRegistry,{
 getByProvider:(provider)=>Effect.fail(new ProviderUnsupportedError({provider})),getByInstance:(provider)=>Effect.fail(new ProviderUnsupportedError({provider})),
 listProviders:()=>Effect.succeed([]),listInstances:()=>Effect.succeed([]),
} satisfies ProviderAdapterRegistryShape);
