/** External agent session imports were removed with their runtimes. */
import {Effect} from "effect";
import type {OrchestrationImportThreadInput} from "@arkos/contracts";
export function makeImportThreadHandler(_options:unknown){return (_input:OrchestrationImportThreadInput)=>Effect.fail(new Error("External agent session import is no longer available."));}
