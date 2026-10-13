/**
 * Public contracts for the Arkos agent-control gateway.
 *
 * New gateway tools decode these schemas before doing any work. Keeping the
 * limits here ensures the MCP surface, server implementation, and tests share
 * the same definition of an exact creation/wait plan.
 */
import { Schema } from "effect";

import { ProjectId, ThreadId, TurnId } from "./baseSchemas";
import { ModelSelection, ProviderKind } from "./orchestration";
import { ProviderModelDescriptor } from "./providerDiscovery";
import { ServerProviderAuthStatus } from "./server";

export const ARKOS_GATEWAY_MAX_THREADS_PER_OPERATION = 20;
export const ARKOS_GATEWAY_MAX_REQUEST_ID_LENGTH = 256;
export const ARKOS_GATEWAY_MAX_WAIT_MS = 60_000;

export const ArkosGatewayErrorCode = Schema.Literals([
  "caller_session_inactive",
  "caller_turn_inactive",
  "capability_denied",
  "provider_unavailable",
  "model_unavailable",
  "model_option_unavailable",
  "idempotency_conflict",
  "creation_plan_locked",
  "creation_limit_exceeded",
  "thread_not_found",
  "wait_timed_out",
  "operation_failed",
]);
export type ArkosGatewayErrorCode = typeof ArkosGatewayErrorCode.Type;

export const ArkosGatewayError = Schema.Struct({
  code: ArkosGatewayErrorCode,
  message: Schema.String,
  details: Schema.optional(Schema.Unknown),
});
export type ArkosGatewayError = typeof ArkosGatewayError.Type;

export const ArkosGatewayErrorResult = Schema.Struct({
  error: ArkosGatewayError,
});
export type ArkosGatewayErrorResult = typeof ArkosGatewayErrorResult.Type;

export const ArkosContextResult = Schema.Struct({
  harness: Schema.Struct({
    name: Schema.Literal("Arkos"),
    policyVersion: Schema.String,
  }),
  caller: Schema.Struct({
    threadId: ThreadId,
    turnId: Schema.NullOr(TurnId),
    provider: ProviderKind,
    projectId: ProjectId,
  }),
  capabilities: Schema.Struct({
    threadRead: Schema.Boolean,
    threadCreate: Schema.Boolean,
    threadWait: Schema.Boolean,
    automations: Schema.Boolean,
  }),
});
export type ArkosContextResult = typeof ArkosContextResult.Type;

export const ArkosCreateThreadSpec = Schema.Struct({
  prompt: Schema.String.check(Schema.isNonEmpty()),
  contextMessageIds: Schema.optional(
    Schema.Array(Schema.String.check(Schema.isNonEmpty())).check(Schema.isMaxLength(16)),
  ),
  notifyCreatorOnComplete: Schema.optional(Schema.Boolean),
  title: Schema.optional(Schema.String.check(Schema.isNonEmpty())),
  target: ModelSelection,
  projectId: Schema.optional(ProjectId),
  environment: Schema.optional(Schema.Literals(["local", "worktree"])),
  baseRef: Schema.optional(Schema.String.check(Schema.isNonEmpty())),
  // Legacy inputs remain decodable for replay/backward compatibility, but the
  // MCP catalog no longer advertises branch-backed worktree creation.
  baseBranch: Schema.optional(Schema.String.check(Schema.isNonEmpty())),
  branchName: Schema.optional(Schema.String.check(Schema.isNonEmpty())),
  runtimeMode: Schema.optional(Schema.Literals(["approval-required", "full-access"])),
  // External integrations need the "computer:control" scope; provider sessions
  // cannot delegate computer control to created threads.
  enableComputerControl: Schema.optional(Schema.Boolean),
});
export type ArkosCreateThreadSpec = typeof ArkosCreateThreadSpec.Type;

const ArkosGatewayRequestId = Schema.String.check(Schema.isNonEmpty()).check(
  Schema.isMaxLength(ARKOS_GATEWAY_MAX_REQUEST_ID_LENGTH),
);

export const ArkosCreateThreadsInput = Schema.Struct({
  requestId: ArkosGatewayRequestId,
  threads: Schema.Array(ArkosCreateThreadSpec)
    .check(Schema.isMinLength(1))
    .check(Schema.isMaxLength(ARKOS_GATEWAY_MAX_THREADS_PER_OPERATION)),
}).annotate({ parseOptions: { onExcessProperty: "error" } });
export type ArkosCreateThreadsInput = typeof ArkosCreateThreadsInput.Type;

export const ArkosProviderCatalog = Schema.Struct({
  provider: ProviderKind,
  defaultModel: Schema.NullOr(Schema.String),
  models: Schema.Array(ProviderModelDescriptor),
  enabled: Schema.Boolean,
  available: Schema.Boolean,
  authStatus: Schema.optional(ServerProviderAuthStatus),
  source: Schema.optional(Schema.String),
  error: Schema.optional(Schema.String),
});
export type ArkosProviderCatalog = typeof ArkosProviderCatalog.Type;

export const ArkosGatewayTargetOptionValue = Schema.Union([
  Schema.String,
  Schema.Number,
  Schema.Boolean,
]);
export type ArkosGatewayTargetOptionValue = typeof ArkosGatewayTargetOptionValue.Type;

export const ArkosGatewayTargetOptionRule = Schema.Struct({
  key: Schema.String,
  valueType: Schema.Literals(["string", "number", "boolean"]),
  allowedValues: Schema.Array(ArkosGatewayTargetOptionValue),
  allowedValuesSource: Schema.Literals(["provider-contract", "model-discovery"]),
});
export type ArkosGatewayTargetOptionRule = typeof ArkosGatewayTargetOptionRule.Type;

export const ArkosGatewayTargetConstruction = Schema.Struct({
  modelValueSource: Schema.Literal("providers[].models[].slug"),
  primaryOptionKey: Schema.String,
  alternativeOptionKeys: Schema.Array(Schema.String),
  optionSelectionRule: Schema.String,
  providerOptions: Schema.Array(ArkosGatewayTargetOptionRule),
  optionsByModel: Schema.Record(Schema.String, Schema.Array(ArkosGatewayTargetOptionRule)),
  exampleTarget: Schema.NullOr(ModelSelection),
});
export type ArkosGatewayTargetConstruction = typeof ArkosGatewayTargetConstruction.Type;

export const ArkosCapabilitiesResult = Schema.Struct({
  targetConstruction: Schema.Record(Schema.String, ArkosGatewayTargetConstruction),
  providers: Schema.Array(ArkosProviderCatalog),
  limits: Schema.Struct({
    maxThreadsPerOperation: Schema.Int,
    maxWaitMs: Schema.Int,
    oneCreationPlanPerActiveTurn: Schema.Boolean,
  }),
});
export type ArkosCapabilitiesResult = typeof ArkosCapabilitiesResult.Type;

export const ArkosCreatedThreadResult = Schema.Struct({
  index: Schema.Int.check(Schema.isGreaterThanOrEqualTo(0)),
  threadId: ThreadId,
  projectId: ProjectId,
  title: Schema.String,
  target: ModelSelection,
  provider: ProviderKind,
  model: Schema.String,
  runtimeMode: Schema.Literals(["approval-required", "full-access"]),
  environment: Schema.Literals(["local", "worktree"]),
  branch: Schema.NullOr(Schema.String),
  worktreePath: Schema.NullOr(Schema.String),
  /** Ready-to-use markdown link target for the created thread
   * (`thread://<threadId>`) — renders as a clickable thread link. */
  link: Schema.optional(Schema.String),
  status: Schema.Literal("task_dispatched"),
});
export type ArkosCreatedThreadResult = typeof ArkosCreatedThreadResult.Type;

export const ArkosCreateThreadsResult = Schema.Struct({
  operationId: Schema.String,
  requestId: ArkosGatewayRequestId,
  requestedCount: Schema.Int.check(Schema.isGreaterThanOrEqualTo(1)),
  createdCount: Schema.Int.check(Schema.isGreaterThanOrEqualTo(0)),
  threadIds: Schema.Array(ThreadId),
  threads: Schema.Array(ArkosCreatedThreadResult),
});
export type ArkosCreateThreadsResult = typeof ArkosCreateThreadsResult.Type;

export const ArkosWaitForThreadsInput = Schema.Struct({
  threadIds: Schema.Array(ThreadId)
    .check(Schema.isMinLength(1))
    .check(Schema.isMaxLength(ARKOS_GATEWAY_MAX_THREADS_PER_OPERATION)),
  runIds: Schema.optional(
    Schema.Array(Schema.NullOr(TurnId)).check(
      Schema.isMaxLength(ARKOS_GATEWAY_MAX_THREADS_PER_OPERATION),
    ),
  ),
  timeoutMs: Schema.optional(
    Schema.Int.check(Schema.isGreaterThanOrEqualTo(0)).check(
      Schema.isLessThanOrEqualTo(ARKOS_GATEWAY_MAX_WAIT_MS),
    ),
  ),
}).annotate({ parseOptions: { onExcessProperty: "error" } });
export type ArkosWaitForThreadsInput = typeof ArkosWaitForThreadsInput.Type;

export const ArkosWaitedThreadResult = Schema.Struct({
  threadId: ThreadId,
  runId: Schema.NullOr(TurnId),
  state: Schema.Literals(["idle", "pending", "running", "completed", "error", "interrupted"]),
  terminal: Schema.Boolean,
  timedOut: Schema.Boolean,
  summary: Schema.NullOr(Schema.String),
  summaryTruncated: Schema.Boolean,
  error: Schema.NullOr(Schema.String),
  readThread: Schema.Struct({
    tool: Schema.Literal("arkos_read_thread"),
    arguments: Schema.Struct({ threadId: ThreadId }),
  }),
});
export type ArkosWaitedThreadResult = typeof ArkosWaitedThreadResult.Type;

export const ArkosWaitForThreadsResult = Schema.Struct({
  callerThreadId: ThreadId,
  runIds: Schema.Array(Schema.NullOr(TurnId)),
  allTerminal: Schema.Boolean,
  timedOut: Schema.Boolean,
  threads: Schema.Array(ArkosWaitedThreadResult),
});
export type ArkosWaitForThreadsResult = typeof ArkosWaitForThreadsResult.Type;
