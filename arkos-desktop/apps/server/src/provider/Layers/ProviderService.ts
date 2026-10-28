/** Session API with no execution runtime connected. */
import {Effect,Layer,Stream} from "effect";
import {ProviderService,type ProviderServiceShape} from "../Services/ProviderService";
import {ProviderValidationError} from "../Errors";
const unavailable=(operation:string)=>Effect.fail(new ProviderValidationError({operation,issue:"No agent runtime is connected.",reason:"runtime-unavailable"}));
export const makeProviderService=(_options?:unknown)=>Effect.succeed({
 startSession:()=>unavailable("startSession"),sendTurn:()=>unavailable("sendTurn"),steerTurn:()=>unavailable("steerTurn"),startReview:()=>unavailable("startReview"),
 interruptTurn:()=>Effect.void,stopTask:()=>unavailable("stopTask"),backgroundTask:()=>unavailable("backgroundTask"),steerSubagent:()=>unavailable("steerSubagent"),
 respondToRequest:()=>unavailable("respondToRequest"),respondToUserInput:()=>unavailable("respondToUserInput"),stopSession:()=>Effect.void,
 listSessions:()=>Effect.succeed([]),getPersistedSessionProfile:()=>Effect.succeed(undefined),getCapabilities:()=>unavailable("getCapabilities"),
 rollbackConversation:()=>unavailable("rollbackConversation"),compactThread:()=>unavailable("compactThread"),closeRuntimeEvents:Effect.void,
 streamEvents:Stream.never,streamPersistedEvents:Stream.never,
} satisfies ProviderServiceShape);
export const makeDurableProviderServiceLive=(_options?:unknown)=>Layer.effect(ProviderService,makeProviderService());
export const ProviderServiceLive=makeDurableProviderServiceLive();
