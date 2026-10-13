import { randomUUID } from "node:crypto";
import { Effect, Layer, Queue, Schema, Stream } from "effect";
import {
  EventId, ProviderRuntimeEvent, RuntimeItemId, TurnId,
  type ProviderSession, type ThreadId,
} from "@arkos/contracts";
import { CodexAdapter, type CodexAdapterShape } from "../Services/CodexAdapter";
import { ProviderAdapterRequestError } from "../Errors";
import type { ProviderThreadSnapshot } from "../Services/ProviderAdapter";

// Preserve the copied renderer protocol: Electron backs the default local slot with AIAgent.
export const hasArkosPythonBridge = () => Boolean(process.env.ARKOS_PYTHON_BRIDGE_URL);

export async function arkosBridgeRequest(path: string, body: unknown = {}) {
  const endpoint = process.env.ARKOS_PYTHON_BRIDGE_URL;
  const token = process.env.ARKOS_PYTHON_BRIDGE_TOKEN;
  if (!endpoint || !token) throw new Error("Electron Python bridge is unavailable");
  const response = await fetch(new URL(path, endpoint), {
    method: "POST", headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
    signal: path === "/turn" ? undefined : AbortSignal.timeout(100_000),
  });
  if (!response.ok) throw new Error(`Arkos Python: ${await response.text()}`);
  return response;
}

export const ArkosAdapterLive = Layer.effect(CodexAdapter, Effect.gen(function* () {
  const events = yield* Queue.bounded<ProviderRuntimeEvent>(2_048);
  const sessions = new Map<ThreadId, ProviderSession>();
  const snapshots = new Map<ThreadId, ProviderThreadSnapshot>();
  const active = new Map<ThreadId, AbortController>();
  const decode = Schema.decodeUnknownSync(ProviderRuntimeEvent);
  const failure = (method: string, cause: unknown) => new ProviderAdapterRequestError({
    provider: "codex", method, detail: String(cause), cause,
  });
  const request = (path: string, body: unknown) => Effect.tryPromise({
    try: () => arkosBridgeRequest(path, body), catch: (cause) => failure(path, cause),
  });
  const emit = async (threadId: ThreadId, type: string, payload: unknown, turnId?: TurnId, itemId?: string) => {
    const session = sessions.get(threadId);
    await Effect.runPromise(Queue.offer(events, decode({
      type, payload, eventId: EventId.makeUnsafe(randomUUID()), provider: "codex", threadId,
      createdAt: new Date().toISOString(),
      ...(session?.providerInstanceId ? { providerInstanceId: session.providerInstanceId } : {}),
      ...(turnId ? { turnId } : {}), ...(itemId ? { itemId: RuntimeItemId.makeUnsafe(itemId) } : {}),
    })));
  };
  const adapter: CodexAdapterShape = {
    provider: "codex",
    capabilities: { sessionModelSwitch: "unsupported", conversationRollback: "restart-session" },
    startSession: (input) => Effect.gen(function* () {
      if (input.resumeCursor) return yield* Effect.fail(failure("start", "Engine resume is not supported; start a new chat."));
      yield* request("/start", { session: input.threadId, cwd: input.cwd });
      const now = new Date().toISOString();
      const session: ProviderSession = {
        provider: "codex", threadId: input.threadId, runtimeMode: input.runtimeMode,
        status: "ready", createdAt: now, updatedAt: now,
        ...(input.cwd ? { cwd: input.cwd } : {}),
        ...(input.providerInstanceId ? { providerInstanceId: input.providerInstanceId } : {}),
      };
      sessions.set(input.threadId, session);
      snapshots.set(input.threadId, { threadId: input.threadId, turns: [] });
      yield* Effect.tryPromise({
        try: async () => {
          await emit(input.threadId, "session.started", { message: "Arkos Python engine ready" });
          await emit(input.threadId, "thread.started", { providerThreadId: input.threadId });
        }, catch: (cause) => failure("start", cause),
      });
      return session;
    }),
    sendTurn: (input) => Effect.gen(function* () {
      const session = sessions.get(input.threadId);
      if (!session) return yield* Effect.fail(failure("turn", "Start an engine session first"));
      if (session.activeTurnId) return yield* Effect.fail(failure("turn", "A turn is already running"));
      if (input.attachments?.length || input.skills?.length || input.mentions?.length)
        return yield* Effect.fail(failure("turn", "The local bridge currently accepts text turns only."));
      const turnId = TurnId.makeUnsafe(randomUUID());
      const itemId = `arkos-${turnId}`;
      const response = yield* request("/turn", { session: input.threadId, turnId, input: input.input || "" });
      sessions.set(input.threadId, { ...session, status: "running", activeTurnId: turnId });
      const controller = new AbortController();
      active.set(input.threadId, controller);
      void (async () => {
        let text = "";
        let settled = false;
        try {
          await emit(input.threadId, "turn.started", {}, turnId);
          await emit(input.threadId, "item.started", { itemType: "assistant_message", status: "inProgress" }, turnId, itemId);
          if (!response.body) throw new Error("Python bridge returned no event stream");
          const reader = response.body.getReader();
          controller.signal.addEventListener("abort", () => { void reader.cancel(); }, { once: true });
          const decoder = new TextDecoder();
          let pending = "";
          while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            pending += decoder.decode(value, { stream: true });
            let newline: number;
            while ((newline = pending.indexOf("\n")) >= 0) {
              const line = pending.slice(0, newline);
              pending = pending.slice(newline + 1);
              if (!line.trim()) continue;
              const event = JSON.parse(line);
              if (event.event === "delta") {
                text += String(event.text);
                await emit(input.threadId, "content.delta", { streamKind: "assistant_text", delta: String(event.text) }, turnId, itemId);
              } else if (event.event === "completed") {
                const error = event.error ? String(event.error) : undefined;
                await emit(input.threadId, "item.completed", {
                  itemType: "assistant_message", status: error ? "failed" : "completed", detail: text,
                }, turnId, itemId);
                await emit(input.threadId, "turn.completed", {
                  state: error ? "failed" : event.interrupted ? "interrupted" : "completed",
                  ...(error ? { errorMessage: error } : {}),
                }, turnId);
                settled = true;
              } else if (event.event === "fatal" || event.event === "rejected") throw new Error(String(event.message));
            }
          }
          if (!settled && !controller.signal.aborted) throw new Error("Python stream ended before completion");
        } catch (cause) {
          if (!settled) await emit(input.threadId, "turn.completed", { state: "failed", errorMessage: String(cause) }, turnId);
        } finally {
          active.delete(input.threadId);
          const current = sessions.get(input.threadId);
          if (current) {
            const { activeTurnId: _turn, ...rest } = current;
            sessions.set(input.threadId, { ...rest, status: "ready", updatedAt: new Date().toISOString() });
          }
          const snapshot = snapshots.get(input.threadId);
          if (snapshot) snapshots.set(input.threadId, { ...snapshot, turns: [...snapshot.turns,
            { id: turnId, items: [{ type: "message", role: "assistant", content: text }], status: "completed" }] });
        }
      })().catch((cause) => console.error("[Arkos bridge] event delivery failed", cause));
      return { threadId: input.threadId, turnId };
    }),
    interruptTurn: (threadId) => request("/interrupt", { session: threadId }).pipe(Effect.asVoid),
    respondToRequest: () => Effect.fail(failure("approval", "No engine approval request is pending")),
    respondToUserInput: () => Effect.fail(failure("input", "No engine input request is pending")),
    stopSession: (threadId) => Effect.gen(function* () {
      if (!sessions.has(threadId)) return;
      yield* request("/stop", { session: threadId });
      active.get(threadId)?.abort();
      sessions.delete(threadId);
      snapshots.delete(threadId);
    }),
    listSessions: () => Effect.sync(() => [...sessions.values()]),
    hasSession: (threadId) => Effect.sync(() => sessions.has(threadId)),
    readThread: (threadId) => snapshots.has(threadId)
      ? Effect.succeed(snapshots.get(threadId)!) : Effect.fail(failure("read", "Unknown engine session")),
    rollbackThread: () => Effect.fail(failure("rollback", "Restart the engine session to roll back")),
    stopAll: () => Effect.forEach([...sessions.keys()], (id) => adapter.stopSession(id), { discard: true }),
    streamEvents: Stream.fromQueue(events),
  };
  yield* Effect.addFinalizer(() => adapter.stopAll().pipe(Effect.catch(() => Effect.void)));
  return adapter;
}));
