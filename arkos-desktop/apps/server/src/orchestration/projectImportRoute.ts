import {Effect} from "effect";
import type {ListProjectImportsInput,ImportProjectInput,LoadProjectImportHistoryInput} from "@arkos/contracts";
export function makeProjectImportHandlers(_options:unknown){return {
 listProjectImports:(_input:ListProjectImportsInput)=>Effect.succeed({projects:[],sources:[]}),
 importProject:(_input:ImportProjectInput)=>Effect.fail(new Error("External agent project import is no longer available.")),
 loadProjectImportHistory:(_input:LoadProjectImportHistoryInput)=>Effect.succeed({messages:[],nextCursor:null}),
};}
