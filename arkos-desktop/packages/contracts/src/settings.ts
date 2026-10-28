import { Schema } from "effect";
import { IsoDateTime, TrimmedString } from "./baseSchemas";
import { DEFAULT_GIT_TEXT_GENERATION_MODEL } from "./model";
import { ModelSelection, ProviderKind, ThreadEnvironmentMode } from "./orchestration";
import { ProviderInstanceConfigMap, ProviderInstanceId } from "./providerInstance";
export const EngineServerSettings=Schema.Struct({enabled:Schema.Boolean.pipe(Schema.withDecodingDefault(()=>true))});
const StringSetting = TrimmedString.check(Schema.isMaxLength(4096));


// How long an idle side chat stays usable before the server expires it.
export const SidechatExpiry = Schema.Literals(["1h", "24h", "never"]);
export type SidechatExpiry = typeof SidechatExpiry.Type;
export const SourceControlWritingStyle = Schema.Literals(["repository", "conventional", "custom"]);
export type SourceControlWritingStyle = typeof SourceControlWritingStyle.Type;
export const MAX_SOURCE_CONTROL_CUSTOM_INSTRUCTIONS_LENGTH = 4096;
export const SourceControlCustomInstructions = Schema.String.check(Schema.isMaxLength(MAX_SOURCE_CONTROL_CUSTOM_INSTRUCTIONS_LENGTH));


























const DisabledSkillNames = Schema.Array(Schema.String.check(Schema.isMaxLength(256))).pipe(Schema.withDecodingDefault(() => []));
// User-level skill toggles. Skills are keyed by lowercased name because the
// unified catalog dedupes provider copies of the same skill by name.
export const SkillsServerSettings = Schema.Struct({
    disabled: DisabledSkillNames,
});
export type SkillsServerSettings = typeof SkillsServerSettings.Type;
// Keep-awake behaviour for macOS `caffeinate`. "agent" keeps the machine awake
// only while at least one agent turn is running.
export const KeepAwakeMode = Schema.Literals(["always", "agent", "off"]);
export type KeepAwakeMode = typeof KeepAwakeMode.Type;
export const DEFAULT_KEEP_AWAKE_MODE: KeepAwakeMode = "off";
export const ServerSettings = Schema.Struct({
    enableAssistantStreaming: Schema.Boolean.pipe(Schema.withDecodingDefault(() => true)),
    enableProviderUpdateChecks: Schema.Boolean.pipe(Schema.withDecodingDefault(() => true)),
    keepAwakeMode: KeepAwakeMode.pipe(Schema.withDecodingDefault(() => DEFAULT_KEEP_AWAKE_MODE)),
    lowerProviderProcessPriority: Schema.Boolean.pipe(Schema.withDecodingDefault(() => true)),
    defaultThreadEnvMode: ThreadEnvironmentMode.pipe(Schema.withDecodingDefault(() => "local")),
    addProjectBaseDirectory: StringSetting.pipe(Schema.withDecodingDefault(() => "")),
    // The GitHub inbox reads one repository per project (the preferred remote). When true it also
    // reads the project's other GitHub remotes, such as the upstream of a fork.
    githubInboxIncludeUpstreams: Schema.Boolean.pipe(Schema.withDecodingDefault(() => false)),
    sidechatExpiry: SidechatExpiry.pipe(Schema.withDecodingDefault(() => "1h")),
    sourceControlWritingStyle: SourceControlWritingStyle.pipe(Schema.withDecodingDefault(() => "repository")),
    sourceControlCustomInstructions: SourceControlCustomInstructions.pipe(Schema.withDecodingDefault(() => "")),
    textGenerationModelSelection: ModelSelection.pipe(Schema.withDecodingDefault(() => ({
        provider: "arkos" as const,
        model: DEFAULT_GIT_TEXT_GENERATION_MODEL,
    }))),
    providers: Schema.Struct({
        arkos: EngineServerSettings.pipe(Schema.withDecodingDefault(() => ({})))
    }).pipe(Schema.withDecodingDefault(() => ({}))),
    providerInstances: ProviderInstanceConfigMap.pipe(Schema.withDecodingDefault(() => ({}))),
    skills: SkillsServerSettings.pipe(Schema.withDecodingDefault(() => ({}))),
    // When the first-run welcome tour was completed or skipped. Server-backed so a
    // browser-storage reset does not replay setup on an already configured install.
    onboardingCompletedAt: Schema.optionalKey(Schema.NullOr(IsoDateTime)),
});
export type ServerSettings = typeof ServerSettings.Type;
export const DEFAULT_SERVER_SETTINGS: ServerSettings = Schema.decodeSync(ServerSettings)({});
// Public settings are structurally separate so the RPC contract can remain an
// explicitly redacted boundary if server-only settings gain more fields later.
export const ServerSettingsView = ServerSettings;
export type ServerSettingsView = typeof ServerSettingsView.Type;
export const DEFAULT_SERVER_SETTINGS_VIEW: ServerSettingsView = Schema.decodeSync(ServerSettingsView)({});
const ModelSelectionPatch = Schema.Struct({
    provider: Schema.optionalKey(ProviderKind),
    instanceId: Schema.optionalKey(ProviderInstanceId),
    model: Schema.optionalKey(Schema.String.check(Schema.isMaxLength(256))),
    options: Schema.optionalKey(Schema.Unknown),
});

export const ServerSettingsPatch = Schema.Struct({
    enableAssistantStreaming: Schema.optionalKey(Schema.Boolean),
    enableProviderUpdateChecks: Schema.optionalKey(Schema.Boolean),
    keepAwakeMode: Schema.optionalKey(KeepAwakeMode),
    lowerProviderProcessPriority: Schema.optionalKey(Schema.Boolean),
    defaultThreadEnvMode: Schema.optionalKey(ThreadEnvironmentMode),
    addProjectBaseDirectory: Schema.optionalKey(StringSetting),
    githubInboxIncludeUpstreams: Schema.optionalKey(Schema.Boolean),
    sidechatExpiry: Schema.optionalKey(SidechatExpiry),
    sourceControlWritingStyle: Schema.optionalKey(SourceControlWritingStyle),
    sourceControlCustomInstructions: Schema.optionalKey(SourceControlCustomInstructions),
    textGenerationModelSelection: Schema.optionalKey(ModelSelectionPatch),
    providers: Schema.optionalKey(Schema.Struct({
        arkos: Schema.optionalKey(Schema.Struct({})),
    })),
    providerInstances: Schema.optionalKey(ProviderInstanceConfigMap),
    skills: Schema.optionalKey(Schema.Struct({
        disabled: Schema.optionalKey(Schema.Array(Schema.String.check(Schema.isMaxLength(256)))),
    })),
    onboardingCompletedAt: Schema.optionalKey(Schema.NullOr(IsoDateTime)),
});
export type ServerSettingsPatch = typeof ServerSettingsPatch.Type;
export class ServerSettingsError extends Schema.TaggedErrorClass<ServerSettingsError>()("ServerSettingsError", {
    settingsPath: Schema.String,
    detail: Schema.String,
    cause: Schema.optional(Schema.Defect),
}) {
    override get message(): string {
        return `Server settings error at ${this.settingsPath}: ${this.detail}`;
    }
}
