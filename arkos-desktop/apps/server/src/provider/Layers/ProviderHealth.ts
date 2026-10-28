/** No agent runtime is connected in this removal-only phase. */
import { ServerProviderUpdateError } from "@arkos/contracts";
import { Effect, Layer, Stream } from "effect";
import { ProviderHealth, type ProviderHealthShape } from "../Services/ProviderHealth";
export const ProviderHealthLive=Layer.succeed(ProviderHealth,{
 getStatuses:Effect.succeed([]),refresh:Effect.succeed([]),streamChanges:Stream.empty,
 updateProvider:(input)=>Effect.fail(new ServerProviderUpdateError({provider:input.provider,reason:"No agent runtime is connected."})),
} satisfies ProviderHealthShape);
