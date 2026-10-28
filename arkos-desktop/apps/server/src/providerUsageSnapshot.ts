import {Effect} from "effect";
import type {ServerGetProviderUsageSnapshotInput,ServerGetProviderUsageSnapshotResult} from "@arkos/contracts";
export const getProviderUsageSnapshot=(_input:ServerGetProviderUsageSnapshotInput):Effect.Effect<ServerGetProviderUsageSnapshotResult>=>Effect.succeed(null);
