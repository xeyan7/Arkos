/** No external agent event source is installed. */
import {Effect,Layer} from "effect";
import {ProviderRuntimeIngestionService,type ProviderRuntimeIngestionShape} from "../Services/ProviderRuntimeIngestion";
export const ProviderRuntimeIngestionLive=Layer.succeed(ProviderRuntimeIngestionService,{start:Effect.void,drain:Effect.void,reconcileSettledOpenTurns:Effect.void} satisfies ProviderRuntimeIngestionShape);
