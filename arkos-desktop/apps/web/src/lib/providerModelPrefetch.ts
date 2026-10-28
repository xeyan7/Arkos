import {resolveProviderDiscoveryCwd} from "./providerDiscovery";
import type {QueryClient} from "@tanstack/react-query";
import type {ProviderKind} from "@arkos/contracts";
import type {DraftThreadEnvMode} from "../composerDraftDomain";
export type ProviderModelPrefetchSettings=unknown;
export function resolveNewThreadModelPrefetchProvider(_input:unknown):ProviderKind{return "arkos";}
export function resolveNewThreadModelPrefetchCwd(input: {
    /** options.worktreePath from the new-thread call (only meaningful with hasExplicitWorktreePath). */
    worktreePath?: string | null | undefined;
    /** True when the caller passed options.worktreePath (even as null) — explicit intent always wins. */
    hasExplicitWorktreePath?: boolean;
    /** options.fresh — a forced-fresh thread never inherits the stored draft's worktree. */
    fresh?: boolean;
    /** options.envMode — "local" clears the draft worktree unless one is passed explicitly. */
    envMode?: DraftThreadEnvMode | null;
    draftWorktreePath?: string | null | undefined;
    projectCwd?: string | null | undefined;
    serverCwd?: string | null | undefined;
}): string | null {
    // Mirrors the new thread's real worktree resolution:
    // - buildDraftThreadContextPatch (threadBootstrap): explicit worktreePath wins,
    //   envMode "local" without an explicit worktree clears it.
    // - createFreshDraftThreadSeed: fresh seeds ignore the stored draft entirely.
    let worktreePath: string | null;
    if (input.hasExplicitWorktreePath === true) {
        worktreePath = input.worktreePath ?? null;
    }
    else if (input.fresh === true) {
        worktreePath = null;
    }
    else if (input.envMode === "local") {
        worktreePath = null;
    }
    else {
        worktreePath = input.draftWorktreePath ?? null;
    }
    return resolveProviderDiscoveryCwd({
        activeThreadWorktreePath: worktreePath,
        activeProjectCwd: input.projectCwd ?? null,
        serverCwd: input.serverCwd ?? null,
    });
}
export function prefetchProviderModelsForNewThread(_client:QueryClient,_input:unknown):void{}
export function prefetchModelsForNewThread(_client:QueryClient,_input:unknown):void{}
