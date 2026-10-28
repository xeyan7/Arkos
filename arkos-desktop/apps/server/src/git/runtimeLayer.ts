import { Effect, Layer } from "effect";
import { GitCoreLive } from "./Layers/GitCore";
import { GitHubCliLive } from "./Layers/GitHubCli";
import { GitManagerLive } from "./Layers/GitManager";
import { GitStatusBroadcasterLive } from "./Layers/GitStatusBroadcaster";
import { TextGeneration, type TextGenerationShape } from "./Services/TextGeneration";
import { TextGenerationError } from "./Errors";
const unavailable=(operation:string)=>Effect.fail(new TextGenerationError({operation,detail:"No agent runtime is connected."}));
export const TextGenerationLayerLive=Layer.succeed(TextGeneration,{
 generateCommitMessage:()=>unavailable("generateCommitMessage"),generatePrContent:()=>unavailable("generatePrContent"),
 generateDiffSummary:()=>unavailable("generateDiffSummary"),generateBranchName:()=>unavailable("generateBranchName"),
 generateThreadTitle:()=>unavailable("generateThreadTitle"),generateThreadRecap:()=>unavailable("generateThreadRecap"),
 generateProjectDigest:()=>unavailable("generateProjectDigest"),generateAutomationIntent:()=>unavailable("generateAutomationIntent"),
 evaluateAutomationCompletion:()=>unavailable("evaluateAutomationCompletion"),
} satisfies TextGenerationShape);
export const GitManagerLayerLive = GitManagerLive.pipe(
  Layer.provideMerge(GitCoreLive),
  Layer.provideMerge(GitHubCliLive),
  Layer.provideMerge(TextGenerationLayerLive),
);

export const GitStatusBroadcasterLayerLive = GitStatusBroadcasterLive.pipe(
  Layer.provide(Layer.mergeAll(GitCoreLive, GitManagerLayerLive)),
);

export const GitLayerLive = Layer.mergeAll(
  GitCoreLive,
  GitHubCliLive,
  GitManagerLayerLive,
  GitStatusBroadcasterLayerLive,
);

