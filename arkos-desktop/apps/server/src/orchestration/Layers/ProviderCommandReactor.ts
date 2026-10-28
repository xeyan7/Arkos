/** External agent execution workers have been removed. */
import {Effect,Layer} from "effect";
import {ProviderCommandReactor,type ProviderCommandReactorShape} from "../Services/ProviderCommandReactor";
export const makeProviderCommandReactorLive=(_options?:unknown)=>Layer.succeed(ProviderCommandReactor,{
 start:Effect.void,drain:Effect.void,listBlockingDeliveries:()=>Effect.succeed([]),reconcileDelivery:()=>Effect.succeed(null),
 regenerateThreadTitle:()=>Effect.fail(new Error("No agent runtime is connected.")),
} satisfies ProviderCommandReactorShape);
export const ProviderCommandReactorLive=makeProviderCommandReactorLive();
