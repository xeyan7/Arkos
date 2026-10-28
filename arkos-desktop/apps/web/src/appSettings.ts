import {normalizeUiDensity as normalizeUiDensityValue} from "./lib/appDensity";
import {normalizeChatWidthMode as normalizeChatWidthModeValue} from "./lib/chatWidth";
import {normalizeRailItemOrder,normalizeHiddenRailItems} from "./appRail.logic";
// FILE: appSettings.ts
// Purpose: Normalizes persisted UI settings and maps them to server/provider options.
// Layer: Web settings state
// Exports: app setting schema, normalization helpers, provider option builders
// FILE: appSettings.ts
// Purpose: Normalizes persisted UI settings and maps them to server/provider options.
// Layer: Web settings state
// Exports: app setting schema, normalization helpers, provider option builders
// FILE: appSettings.ts
// Purpose: Normalizes persisted UI settings and maps them to server/provider options.
// Layer: Web settings state
// Exports: app setting schema, normalization helpers, provider option builders
// FILE: appSettings.ts
// Purpose: Normalizes persisted UI settings and maps them to server/provider options.
// Layer: Web settings state
// Exports: app setting schema, normalization helpers, provider option builders
import { useCallback, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Option, Schema, SchemaTransformation } from "effect";
import { type AssistantDeliveryMode, DesktopAppIcon, DEFAULT_GIT_TEXT_GENERATION_MODEL, DEFAULT_SERVER_SETTINGS_VIEW, ProviderInstanceConfigMap, type ProviderDriverKind, ProviderInstanceId, GitHubInboxSort, KeepAwakeMode, TrimmedNonEmptyString, ProviderKind, SidechatExpiry, SourceControlWritingStyle, SourceControlCustomInstructions, type ProviderStartOptions, type ServerSettingsView, type ServerSettingsPatch } from "@arkos/contracts";
import { getDefaultModel, resolveSelectableModel } from "@arkos/shared/model";
import { APP_SNAP_SHORTCUT_KEYS, APP_SNAP_SHORTCUT_MODIFIERS, DEFAULT_APP_SNAP_SHORTCUT } from "@arkos/shared/appSnapShortcut";
import type { ArkosDesktopFlavor } from "@arkos/shared/desktopIdentity";
import { useLocalStorage } from "./hooks/useLocalStorage";
import { EnvMode } from "./components/BranchToolbar.logic";
import { type ProviderModelOption } from "./providerModelOptions";
import { DEFAULT_PROVIDER_ORDER } from "./providerOrdering";
import { DEFAULT_HIDDEN_RAIL_ITEMS, RAIL_ORDERABLE_ITEM_IDS } from "./appRail.logic";
import { ensureNativeApi } from "./nativeApi";
import { githubInboxQueryKeys } from "./lib/githubInboxQueryOptions";
import { providerDiscoveryQueryKeys } from "./lib/providerDiscoveryReactQuery";
import { invalidateProviderUsageQueries, reconcileServerProviderStatuses, serverQueryKeys, serverSettingsQueryOptions } from "./lib/serverReactQuery";
import { DEFAULT_UI_DENSITY, UI_DENSITY_MODES } from "./lib/appDensity";
import { DEFAULT_CHAT_WIDTH, CHAT_WIDTH_MODES } from "./lib/chatWidth";
const APP_SETTINGS_STORAGE_KEY = "arkos:app-settings:v1";
const SERVER_SETTINGS_MIGRATION_STORAGE_KEY = "arkos:server-settings-migrated:v1";
function hasCompletedServerSettingsMigration(): boolean {
    return globalThis.localStorage?.getItem(SERVER_SETTINGS_MIGRATION_STORAGE_KEY) === "1";
}
const MAX_CUSTOM_MODEL_COUNT = 32;
export const MAX_CUSTOM_MODEL_LENGTH = 256;
export const MIN_CHAT_FONT_SIZE_PX = 11;
export const MAX_CHAT_FONT_SIZE_PX = 18;
export const DEFAULT_CHAT_FONT_SIZE_PX = 13;
export const MIN_TERMINAL_FONT_SIZE_PX = 10;
export const MAX_TERMINAL_FONT_SIZE_PX = 22;
export const DEFAULT_TERMINAL_FONT_SIZE_PX = 12;
// Terminal font is a free-form font-family value: the user can type any font
// installed on their machine. An empty value keeps the bundled default stack
// (defined in index.css). The list below is only autocomplete inspiration shown
// in the settings input — it does NOT restrict what can be entered.
export const DEFAULT_TERMINAL_FONT_FAMILY = "";
export const TERMINAL_FONT_FAMILY_SUGGESTIONS: ReadonlyArray<string> = [
    "JetBrains Mono",
    "Fira Code",
    "Cascadia Code",
    "SF Mono",
    "Menlo",
    "Source Code Pro",
    "IBM Plex Mono",
    "Hack",
    "Roboto Mono",
    "Ubuntu Mono",
    "Consolas",
];
export const TimestampFormat = Schema.Literals(["locale", "12-hour", "24-hour"]);
export type TimestampFormat = typeof TimestampFormat.Type;
export const DEFAULT_TIMESTAMP_FORMAT: TimestampFormat = "locale";
export const SidebarProjectSortOrder = Schema.Literals(["updated_at", "created_at", "manual"]);
export type SidebarProjectSortOrder = typeof SidebarProjectSortOrder.Type;
export const DEFAULT_SIDEBAR_PROJECT_SORT_ORDER: SidebarProjectSortOrder = "manual";
export const SidebarThreadSortOrder = Schema.Literals(["updated_at", "created_at"]);
export const ComputerPreviewSize = Schema.Literals(["compact", "large"]);
export type ComputerPreviewSize = typeof ComputerPreviewSize.Type;
export const DEFAULT_COMPUTER_PREVIEW_SIZE: ComputerPreviewSize = "compact";
export const AgentCursorColorMode = Schema.Literals(["stock", "custom"]);
export type AgentCursorColorMode = typeof AgentCursorColorMode.Type;
export const DEFAULT_AGENT_CURSOR_COLOR_MODE: AgentCursorColorMode = "stock";
/**
 * A persisted id list that keeps the entries this build can resolve (known ids, or a
 * renamed id's new name) and drops the rest, so an id written by a newer or older build
 * never fails the whole settings decode and resets every setting.
 */
function persistedIdList<Id extends string>(IdSchema: Schema.Codec<Id>, resolve: (value: string) => Id | undefined) {
    return Schema.Array(Schema.String).pipe(Schema.decodeTo(Schema.Array(IdSchema), SchemaTransformation.transform<ReadonlyArray<Id>, ReadonlyArray<string>>({
        decode: (values) => values.flatMap((value) => {
            const id = resolve(value);
            return id === undefined ? [] : [id];
        }),
        encode: (values) => values,
    })));
}
function persistedKnownIdList<const Ids extends ReadonlyArray<string>>(ids: Ids) {
    const Id = Schema.Literals([...ids]);
    const isKnownId = Schema.is(Id);
    return persistedIdList(Id, (value) => (isKnownId(value) ? value : undefined));
}
const RailOrderableItemIdList = persistedKnownIdList(RAIL_ORDERABLE_ITEM_IDS);
/** Where the Tasks entry opens: the to-do list or the Kanban board of chats. */
export const TasksViewMode = Schema.Literals(["list", "kanban"]);
export type TasksViewMode = typeof TasksViewMode.Type;
export const DEFAULT_TASKS_VIEW_MODE: TasksViewMode = "list";
export type SidebarThreadSortOrder = typeof SidebarThreadSortOrder.Type;
export const DEFAULT_SIDEBAR_THREAD_SORT_ORDER: SidebarThreadSortOrder = "updated_at";
export const FollowUpBehavior = Schema.Literals(["queue", "steer"]);
/** The inbox status filter. Merged is the closed list narrowed to merged pull requests. */
export const GitHubInboxStateFilter = Schema.Literals(["open", "closed", "merged"]);
export type GitHubInboxStateFilter = typeof GitHubInboxStateFilter.Type;
/** GitHub inbox kind filter: both kinds, or only pull requests or only issues. */
export const GitHubInboxKindFilter = Schema.Literals(["all", "pullRequest", "issue"]);
export type GitHubInboxKindFilter = typeof GitHubInboxKindFilter.Type;
/** GitHub inbox involvement filter, applied on the client over the loaded superset. */
export const GitHubInboxInvolvementFilter = Schema.Literals([
    "everything",
    "involved",
    "reviewRequested",
    "authored",
    "assigned",
]);
export type GitHubInboxInvolvementFilter = typeof GitHubInboxInvolvementFilter.Type;
/** Where a plain click on a GitHub pull request or issue link opens: the built-in review view,
 *  the in-app browser, or the system browser. */
export const GitHubLinkOpenTarget = Schema.Literals(["app", "browser", "external"]);
export type GitHubLinkOpenTarget = typeof GitHubLinkOpenTarget.Type;
export const DEFAULT_GITHUB_LINK_OPEN_TARGET: GitHubLinkOpenTarget = "app";
export type FollowUpBehavior = typeof FollowUpBehavior.Type;
// Sound the chat message trail moves with (desktop on macOS).
export const MessageTrailAudioSource = Schema.Literals(["off", "system", "microphone", "both"]);
export type MessageTrailAudioSource = typeof MessageTrailAudioSource.Type;
export const DEFAULT_FOLLOW_UP_BEHAVIOR: FollowUpBehavior = "queue";
/** Which account windows each app-rail usage ring draws: both, or only one of them. */
export const RailUsageWindow = Schema.Literals(["both", "fiveHour", "weekly"]);
export type RailUsageWindow = typeof RailUsageWindow.Type;
export const DEFAULT_RAIL_USAGE_WINDOW: RailUsageWindow = "both";
// What plain Enter does while a composer voice note is recording: "stop" only
// transcribes into the draft, "send" also sends the draft once transcribed.
export const VoiceEnterBehavior = Schema.Literals(["stop", "send"]);
export type VoiceEnterBehavior = typeof VoiceEnterBehavior.Type;
export const DEFAULT_VOICE_ENTER_BEHAVIOR: VoiceEnterBehavior = "stop";
export const UiDensity = Schema.Literals(UI_DENSITY_MODES);
export type UiDensity = typeof UiDensity.Type;
export { DEFAULT_UI_DENSITY };
export const ChatWidthMode = Schema.Literals(CHAT_WIDTH_MODES);
export type ChatWidthMode = typeof ChatWidthMode.Type;
export { DEFAULT_CHAT_WIDTH };
const AppSnapShortcut = Schema.Union([
    Schema.Struct({ kind: Schema.Literal("both-option-keys") }),
    Schema.Struct({
        kind: Schema.Literal("key-chord"),
        modifier: Schema.Literals(APP_SNAP_SHORTCUT_MODIFIERS),
        key: Schema.Literals(APP_SNAP_SHORTCUT_KEYS),
    }),
]);
export function getDefaultNativeFontSmoothing(platform = globalThis.navigator?.platform ?? "") {
    return /mac|iphone|ipad|ipod/i.test(platform);
}
const withDefaults = <S extends Schema.Top & Schema.WithoutConstructorDefault, D extends S["~type.make.in"] & S["Encoded"],>(fallback: () => D) => (schema: S) => schema.pipe(Schema.withConstructorDefault(() => Option.some(fallback())), Schema.withDecodingDefault(() => fallback()));
const PersistedProviderKind = Schema.String.pipe(Schema.decodeTo(ProviderKind, SchemaTransformation.transform({ decode: (_value: string): "arkos" => "arkos", encode: (value: "arkos"): string => value })));
// gemini was renamed to antigravity, so its list entries carry over. Removed
// providers with no successor subscription (kilo) must not transfer prefs like
// "hidden" onto another provider, so their list entries are dropped. Unknown
// values are dropped too instead of failing the whole settings decode.
const RENAMED_PROVIDERS: Readonly<Record<string, ProviderKind>> = {};
function resolvePersistedProviderListEntry(provider: string): ProviderKind | undefined {
    const renamed = RENAMED_PROVIDERS[provider] ?? provider;
    return Schema.is(ProviderKind)(renamed) ? renamed : undefined;
}
const PersistedProviderKindList = persistedIdList(ProviderKind, resolvePersistedProviderListEntry);
const isProviderInstanceId = Schema.is(ProviderInstanceId);
const PersistedProviderInstanceIdList = persistedIdList(ProviderInstanceId, (value) => isProviderInstanceId(value) ? value : undefined);
const PersistedHiddenModels = Schema.Array(Schema.Struct({
    provider: Schema.String,
    slug: Schema.String,
})).pipe(Schema.decodeTo(Schema.Array(Schema.Struct({
    provider: ProviderKind,
    slug: Schema.String,
})), SchemaTransformation.transform({
    decode: (entries): ReadonlyArray<{
        provider: ProviderKind;
        slug: string;
    }> => entries.flatMap((entry) => {
        const resolved = resolvePersistedProviderListEntry(entry.provider);
        return resolved === undefined ? [] : [{ provider: resolved, slug: entry.slug }];
    }),
    encode: (entries) => entries,
})));
export const AppSettingsSchema = Schema.Struct({
    // Server-backed first-run marker; see ServerSettings.onboardingCompletedAt.
    onboardingCompletedAt: Schema.NullOr(Schema.String).pipe(withDefaults((): string | null => null)),
    uiDensity: UiDensity.pipe(withDefaults(() => DEFAULT_UI_DENSITY)),
    chatWidth: ChatWidthMode.pipe(withDefaults(() => DEFAULT_CHAT_WIDTH)),
    chatFontSizePx: Schema.Number.pipe(withDefaults(() => DEFAULT_CHAT_FONT_SIZE_PX)),
    chatCodeFontFamily: Schema.String.check(Schema.isMaxLength(256)).pipe(withDefaults(() => "")),
    terminalFontSizePx: Schema.Number.pipe(withDefaults(() => DEFAULT_TERMINAL_FONT_SIZE_PX)),
    terminalFontFamily: Schema.String.check(Schema.isMaxLength(256)).pipe(withDefaults(() => DEFAULT_TERMINAL_FONT_FAMILY)),
    providerInstances: ProviderInstanceConfigMap.pipe(withDefaults(() => ({}))),
    // Deprecated Gemini keys remain decodable until normalization rewrites local storage.
    geminiBinaryPath: Schema.optionalKey(Schema.String.check(Schema.isMaxLength(4096))),
    defaultThreadEnvMode: EnvMode.pipe(withDefaults(() => "local" as const satisfies EnvMode)),
    anchorSentMessagesToTop: Schema.Boolean.pipe(withDefaults(() => true)),
    confirmThreadDelete: Schema.Boolean.pipe(withDefaults(() => true)),
    // Opt-in: archiving a task also releases its worktree when nothing else uses it.
    archiveDeletesOrphanedWorktree: Schema.Boolean.pipe(withDefaults(() => false)),
    // Desktop quit dialog: remember interrupted chats and continue them on the next launch.
    resumeChatsAfterQuit: Schema.Boolean.pipe(withDefaults(() => true)),
    confirmThreadArchive: Schema.Boolean.pipe(withDefaults(() => false)),
    confirmTerminalTabClose: Schema.Boolean.pipe(withDefaults(() => true)),
    diffWordWrap: Schema.Boolean.pipe(withDefaults(() => false)),
    showPullRequestDiffColors: Schema.Boolean.pipe(withDefaults(() => true)),
    githubLinkOpenTarget: GitHubLinkOpenTarget.pipe(withDefaults(() => DEFAULT_GITHUB_LINK_OPEN_TARGET)),
    // Local-only GitHub inbox view state: the filters the page reopens with (URL parameters
    // override them for one visit; search text lives only in the URL). The column widths are not
    // stored: the page always opens at even fractions.
    githubInboxKind: GitHubInboxKindFilter.pipe(withDefaults(() => "all" as const)),
    githubInboxState: GitHubInboxStateFilter.pipe(withDefaults(() => "open" as const)),
    githubInboxSort: GitHubInboxSort.pipe(withDefaults(() => "created" as const)),
    githubInboxInvolvement: GitHubInboxInvolvementFilter.pipe(withDefaults(() => "everything" as const)),
    githubInboxProjectIds: Schema.Array(Schema.String.check(Schema.isMaxLength(512))).pipe(withDefaults(() => [])),
    githubInboxLabels: Schema.Array(Schema.String.check(Schema.isMaxLength(256))).pipe(withDefaults(() => [])),
    // The list sections the user has expanded; the first two start open, the rest collapsed.
    githubInboxExpandedSections: Schema.Array(Schema.Literals(["authored", "reviewRequested", "involved", "others"])).pipe(withDefaults(() => ["authored", "reviewRequested"] as const)),
    // Server-backed: the inbox also reads each project's other GitHub remotes (fork upstreams).
    githubInboxIncludeUpstreams: Schema.Boolean.pipe(withDefaults(() => false)),
    // Server-backed: how long an idle side chat stays usable before it expires.
    sidechatExpiry: SidechatExpiry.pipe(withDefaults(() => "1h" as const satisfies SidechatExpiry)),
    // Local-only UI preferences for hiding sidebar surfaces a user doesn't want.
    // `showChatsSection` controls the standalone "Chats" list in the sidebar footer
    // (rootless chats not tied to a project). `showGroupsSection` controls the
    // optional Groups tab in the section switcher.
    showChatsSection: Schema.Boolean.pipe(withDefaults(() => true)),
    showGroupsSection: Schema.Boolean.pipe(withDefaults(() => true)),
    // Deprecated rename bridge from the Studio surface. Normalization migrates this
    // value onto `showGroupsSection` once and then omits the key.
    showStudioSection: Schema.optionalKey(Schema.Boolean),
    // The view the Tasks entry opens, last picked in its List/Kanban switch.
    // Stable never reads it (Kanban is its only view).
    tasksViewMode: TasksViewMode.pipe(withDefaults(() => DEFAULT_TASKS_VIEW_MODE)),
    // Rail shortcuts the user added from the rail's "…" menu, in rail order:
    // "space:<id>" (the Void key for unfiled) or "project:<id>" (see appRail.logic).
    railShortcuts: Schema.Array(Schema.String.check(Schema.isMaxLength(512))).pipe(withDefaults(() => [])),
    // The rail's Customize state: the order of the rail's top items and the ones the user hid. Home never hides, and an
    // active hidden item stays visible (see appRail.logic).
    railItemOrder: RailOrderableItemIdList.pipe(withDefaults(() => [...RAIL_ORDERABLE_ITEM_IDS])),
    hiddenRailItems: RailOrderableItemIdList.pipe(withDefaults(() => [...DEFAULT_HIDDEN_RAIL_ITEMS])),
    // Whether the per-run threads standalone automations create appear in the sidebar
    // (and the surfaces derived from it: Kanban, Activity, project picker). Runs stay
    // listed on the automation's page and findable via search either way.
    showAutomationRunThreads: Schema.Boolean.pipe(withDefaults(() => true)),
    // Local-only UI preferences: which optional sections of the chat Environment panel are
    // shown. The git block (Changes/Worktree/branch/Commit and Push) is always visible; these
    // toggle the sections beneath it via the panel header's gear menu.
    // When false (default), normal chats start with the Environment panel closed. User toggles
    // also write back here so the last explicit open/close survives reloads.
    environmentPanelDefaultOpen: Schema.Boolean.pipe(withDefaults(() => false)),
    showEnvironmentUsage: Schema.Boolean.pipe(withDefaults(() => true)),
    // Legacy provider selection, retained to migrate existing sidebar preferences.
    railUsageProviders: PersistedProviderKindList.pipe(withDefaults((): ReadonlyArray<ProviderKind> => ["arkos"])),
    // Accounts whose usage rings sit at the bottom of the app rail. Null migrates the
    // legacy provider ids to their default accounts; an empty list explicitly hides all rings.
    railUsageInstanceIds: Schema.NullOr(PersistedProviderInstanceIdList).pipe(withDefaults(() => null)),
    railUsageWindow: RailUsageWindow.pipe(withDefaults(() => DEFAULT_RAIL_USAGE_WINDOW)),
    // Usage popovers (rail rings, chat header, branch toolbar) open on the limit rows only;
    // reset credits, credits, and token totals sit behind a "Details" toggle. The toggle
    // writes back here, so the last choice sticks; Settings → Usage exposes it too.
    usageDetailsDefaultOpen: Schema.Boolean.pipe(withDefaults(() => false)),
    // Which detail sections usage popovers offer at all. Ignored when a provider reports no
    // limit rows, since the details are then the only usage there is to show.
    usagePopoverShowResetCredits: Schema.Boolean.pipe(withDefaults(() => true)),
    usagePopoverShowUsageLines: Schema.Boolean.pipe(withDefaults(() => true)),
    showEnvironmentRepository: Schema.Boolean.pipe(withDefaults(() => true)),
    showEnvironmentPullRequest: Schema.Boolean.pipe(withDefaults(() => true)),
    showEnvironmentEditor: Schema.Boolean.pipe(withDefaults(() => true)),
    showEnvironmentRecap: Schema.Boolean.pipe(withDefaults(() => true)),
    showEnvironmentPinned: Schema.Boolean.pipe(withDefaults(() => true)),
    showEnvironmentInstructions: Schema.Boolean.pipe(withDefaults(() => false)),
    showEnvironmentNotepad: Schema.Boolean.pipe(withDefaults(() => false)),
    followUpBehavior: FollowUpBehavior.pipe(withDefaults(() => DEFAULT_FOLLOW_UP_BEHAVIOR)),
    voiceEnterBehavior: VoiceEnterBehavior.pipe(withDefaults(() => DEFAULT_VOICE_ENTER_BEHAVIOR)),
    enableAssistantStreaming: Schema.Boolean.pipe(withDefaults(() => true)),
    // Fold each finished turn's tool calls and intermediate messages behind one
    // "Worked for…" line. Off keeps every step of finished turns visible.
    collapseFinishedTurns: Schema.Boolean.pipe(withDefaults(() => true)),
    // Started threads: show reasoning effort as a stepped slider card in the composer's
    // model menu instead of radio rows. New chats keep the split model/effort pickers.
    composerEffortSlider: Schema.Boolean.pipe(withDefaults(() => true)),
    // Desktop on macOS: the message trail moves with the Mac's audio output,
    // the microphone, or both. Opt-in because the first use asks macOS for access.
    messageTrailAudioSource: MessageTrailAudioSource.pipe(withDefaults(() => "off" as const)),
    // Core Audio UID of the microphone the trail listens to; "" follows the Mac's
    // default input (which may be a Bluetooth headset).
    messageTrailMicrophoneId: Schema.String.check(Schema.isMaxLength(512)).pipe(withDefaults(() => "")),
    autoOpenDevicePane: Schema.Boolean.pipe(withDefaults(() => true)),
    enableProviderUpdateChecks: Schema.Boolean.pipe(withDefaults(() => true)),
    keepAwakeMode: KeepAwakeMode.pipe(withDefaults(() => "off" as const satisfies KeepAwakeMode)),
    lowerProviderProcessPriority: Schema.Boolean.pipe(withDefaults(() => true)),
    enableNativeFontSmoothing: Schema.Boolean.pipe(withDefaults(getDefaultNativeFontSmoothing)),
    desktopAppIcon: DesktopAppIcon.pipe(withDefaults(() => "default" as const)),
    // Local desktop preference: frameless custom title bar on Windows/Linux.
    // Electron `frame` is fixed at window creation, so the desktop main process also
    // persists this value and a relaunch is required for the live window to match.
    useCustomTitleBar: Schema.Boolean.pipe(withDefaults(() => true)),
    enableTaskCompletionToasts: Schema.Boolean.pipe(withDefaults(() => true)),
    enableSystemTaskCompletionNotifications: Schema.Boolean.pipe(withDefaults(() => true)),
    // Finished-work alerts wait for the agent's background subagents too, and a
    // subagent's own thread never alerts. Off alerts every time any of them stops.
    notifyAfterSubagentsFinish: Schema.Boolean.pipe(withDefaults(() => true)),
    // Local desktop preference. Native capability/permission state remains owned by Electron.
    // AppSnap is opt-in because enabling its Settings toggle requests macOS
    // Input Monitoring and Screen Recording permissions.
    enableAppSnap: Schema.Boolean.pipe(withDefaults(() => false)),
    appSnapShortcut: AppSnapShortcut.pipe(withDefaults(() => DEFAULT_APP_SNAP_SHORTCUT)),
    // Local desktop preference: play the shutter cue when an AppSnap lands in a composer.
    appSnapPlaySound: Schema.Boolean.pipe(withDefaults(() => true)),
    // Deprecated rename bridge. Normalization migrates this value and then omits the key.
    enableAppshots: Schema.optionalKey(Schema.Boolean),
    // Show the in-chat Computer preview when an agent starts driving the desktop.
    autoOpenComputerPane: Schema.Boolean.pipe(withDefaults(() => true)),
    // In-chat computer preview footprint. Compact is the default: a small
    // glanceable card that reserves a narrow gutter. Large restores the
    // previous wide card for users who want the detail inline.
    computerPreviewSize: ComputerPreviewSize.pipe(withDefaults(() => DEFAULT_COMPUTER_PREVIEW_SIZE)),
    // Computer control is off by default. When on, the agent may use the desktop
    // in any chat. Approval gates and Stop still apply.
    computerControlEnabled: Schema.Boolean.pipe(withDefaults(() => false)),
    // The agent cursor's colors. Stock is the default monochrome treatment and
    // stores no overrides; "custom" opts into a fill and rim, persisted as
    // lowercase `#rrggbb` strings and pushed to the desktop cursor host.
    agentCursorColorMode: AgentCursorColorMode.pipe(withDefaults(() => DEFAULT_AGENT_CURSOR_COLOR_MODE)),
    agentCursorFillColor: Schema.String.check(Schema.isMaxLength(7)).pipe(withDefaults(() => "")),
    agentCursorRimColor: Schema.String.check(Schema.isMaxLength(7)).pipe(withDefaults(() => "")),
    // Deprecated rename bridge. Normalization migrates this value and then omits the key.
    allowComputerControlInNewChats: Schema.optionalKey(Schema.Boolean),
    // One-shot composer hint that suggests Medium effort for faster desktop actions.
    // Set when the user applies or dismisses it, so the hint never asks twice.
    dismissedComputerControlEffortHint: Schema.Boolean.pipe(withDefaults(() => false)),
    // One-shot composer hint offering Auto-fix CI on a chat's open PR. Set when the
    // user dismisses it or turns Auto-fix CI on anywhere, so it never asks twice.
    dismissedPullRequestAutoFixHint: Schema.Boolean.pipe(withDefaults(() => false)),
    sidebarProjectSortOrder: SidebarProjectSortOrder.pipe(withDefaults(() => DEFAULT_SIDEBAR_PROJECT_SORT_ORDER)),
    sidebarThreadSortOrder: SidebarThreadSortOrder.pipe(withDefaults(() => DEFAULT_SIDEBAR_THREAD_SORT_ORDER)),
    timestampFormat: TimestampFormat.pipe(withDefaults(() => DEFAULT_TIMESTAMP_FORMAT)),
    customGeminiModels: Schema.optionalKey(Schema.Array(Schema.String)),
    textGenerationProvider: PersistedProviderKind.pipe(withDefaults(() => "arkos" as const)),
    textGenerationProviderInstanceId: Schema.optional(ProviderInstanceId),
    textGenerationModel: Schema.optional(TrimmedNonEmptyString),
    sourceControlWritingStyle: SourceControlWritingStyle.pipe(withDefaults(() => "repository" as const)),
    sourceControlCustomInstructions: SourceControlCustomInstructions.pipe(withDefaults(() => "")),
    uiFontFamily: Schema.String.check(Schema.isMaxLength(256)).pipe(withDefaults(() => "")),
    defaultProvider: PersistedProviderKind.pipe(withDefaults(() => "arkos" as const)),
    // Local-only UI preference: providers explicitly hidden from the composer picker.
    // The active/locked provider for a thread is always shown regardless, so users
    // never get stuck on a thread whose provider they later chose to hide.
    hiddenProviders: PersistedProviderKindList.pipe(withDefaults(() => [])),
    // Server-backed provider shutdown policy. Unlike `hiddenProviders`, entries here
    // cannot run discovery, health checks, updates, or new turns until re-enabled.
    disabledProviders: PersistedProviderKindList.pipe(withDefaults(() => [])),
    // Local-only UI preference: top-level provider order in Settings and the composer picker.
    providerOrder: PersistedProviderKindList.pipe(withDefaults(() => [...DEFAULT_PROVIDER_ORDER])),
    // Deprecated local-only preference kept for backward-compatible decoding.
    // Model-level hiding caused too many edge cases, so the app now normalizes it away.
    hiddenModels: PersistedHiddenModels.pipe(withDefaults(() => [])),
});
export type AppSettings = typeof AppSettingsSchema.Type;
/**
 * First-launch icon default per desktop flavor. The schema keeps "default" so
 * persisted renderer state stays stable; the native side owns first-launch
 * defaulting via getAppIcon, and the Appearance reset uses this for its target.
 */
export function defaultDesktopAppIconForFlavor(flavor: ArkosDesktopFlavor | "unknown"): DesktopAppIcon {
    return flavor === "beta" ? "beta" : "default";
}
/** The settings values and mutation used by a mounted settings panel.
 * The route owns the subscription so extracted workflow panels do not create
 * duplicate local-storage/server-settings subscriptions. */
export type AppSettingsBinding = {
    readonly settings: AppSettings;
    readonly defaults: AppSettings;
    readonly updateSettings: (patch: Partial<AppSettings>) => void;
};
export function isGitTextGenerationSettingsDirty(settings: AppSettings, defaults: AppSettings): boolean {
    return ((settings.textGenerationProvider ?? "arkos") !== (defaults.textGenerationProvider ?? "arkos") ||
        (settings.textGenerationProviderInstanceId ?? settings.textGenerationProvider ?? "arkos") !==
            (defaults.textGenerationProviderInstanceId ?? defaults.textGenerationProvider ?? "arkos") ||
        (settings.textGenerationModel ?? DEFAULT_GIT_TEXT_GENERATION_MODEL) !==
            (defaults.textGenerationModel ?? DEFAULT_GIT_TEXT_GENERATION_MODEL));
}
type Mutable<T> = {
    -readonly [Key in keyof T]: T[Key];
};
type MutableServerSettingsPatch = Mutable<ServerSettingsPatch>;
type MutableServerSettingsProvidersPatch = Mutable<NonNullable<ServerSettingsPatch["providers"]>>;
export interface AppModelOption extends ProviderModelOption {
    provider: ProviderKind;
    isCustom: boolean;
}
const DEFAULT_APP_SETTINGS = AppSettingsSchema.makeUnsafe({});
let serverSettingsMigrationInFlight = false;
// Droid's ACP catalog is authoritative and rejects unknown slugs. Preserve its
// persisted config for compatibility, but do not offer an editor it cannot honor.
export function normalizeChatFontSizePx(value: number | null | undefined): number {
    if (typeof value !== "number" || !Number.isFinite(value)) {
        return DEFAULT_CHAT_FONT_SIZE_PX;
    }
    return Math.min(MAX_CHAT_FONT_SIZE_PX, Math.max(MIN_CHAT_FONT_SIZE_PX, Math.round(value)));
}
export function normalizeTerminalFontSizePx(value: number | null | undefined): number {
    if (typeof value !== "number" || !Number.isFinite(value)) {
        return DEFAULT_TERMINAL_FONT_SIZE_PX;
    }
    return Math.min(MAX_TERMINAL_FONT_SIZE_PX, Math.max(MIN_TERMINAL_FONT_SIZE_PX, Math.round(value)));
}
/** Normalize a cursor color to lowercase `#rrggbb`, or "" for anything else. */
export function normalizeCursorHexColor(value: string | null | undefined): string {
    const candidate = (value ?? "").trim().toLowerCase();
    return /^#[0-9a-f]{6}$/.test(candidate) ? candidate : "";
}
/**
 * The custom agent-cursor colors to push to the desktop cursor host, or null
 * for the stock monochrome cursor. Stock mode resolves to null no matter what
 * colors are stored, so switching back to stock never leaves a stale override
 * in the pushed payload. A channel with no valid color is omitted, not sent
 * empty, because the driver treats an omitted channel as stock.
 */
export function resolveAgentCursorColors(settings: Pick<AppSettings, "agentCursorColorMode" | "agentCursorFillColor" | "agentCursorRimColor">): {
    fill?: string;
    rim?: string;
} | null {
    if ((settings.agentCursorColorMode ?? DEFAULT_AGENT_CURSOR_COLOR_MODE) !== "custom")
        return null;
    const fill = normalizeCursorHexColor(settings.agentCursorFillColor);
    const rim = normalizeCursorHexColor(settings.agentCursorRimColor);
    if (!fill && !rim)
        return null;
    return { ...(fill ? { fill } : {}), ...(rim ? { rim } : {}) };
}
export function normalizeTerminalFontFamily(value: string | null | undefined): string {
    // Free-form font-family text. Only strip characters that can't legitimately
    // appear in a CSS font-family value so the typed name can't break out of the
    // custom property (`;`, `{}`, angle brackets, newlines) or smuggle in other
    // declarations. Whitespace is intentionally preserved here so multi-word names
    // ("Fira Code") remain typable in a controlled input; the CSS resolver trims.
    return (value ?? "").replace(/[;{}<>\n\r]/g, "").slice(0, 256);
}
// Build the CSS font-family stack written to `--terminal-font-family`, or null
// when the bundled default (defined in index.css) should stay in effect.
//
// Accepts either a single family name (`Fira Code`) or a full comma-separated
// stack (`"Fira Code", Menlo, monospace`). Single names are quoted when needed,
// and a `monospace` fallback is appended so an uninstalled font degrades.
export function resolveTerminalFontFamilyStack(value: string | null | undefined): string | null {
    const normalized = normalizeTerminalFontFamily(value).replace(/\s+/g, " ").trim();
    if (!normalized) {
        return null;
    }
    const hasGenericFallback = /\b(?:monospace|serif|sans-serif|system-ui|ui-monospace)\b/.test(normalized);
    if (normalized.includes(",")) {
        return hasGenericFallback ? normalized : `${normalized}, monospace`;
    }
    const isQuoted = /^(["']).*\1$/.test(normalized);
    const family = !isQuoted && /\s/.test(normalized) ? `"${normalized}"` : normalized;
    return hasGenericFallback ? family : `${family}, monospace`;
}
export interface ProviderInstanceOption {
    readonly instanceId: ProviderInstanceId;
    readonly provider: ProviderKind;
    readonly driver: ProviderKind;
    readonly label: string;
    /** User-picked `#rrggbb` marker shown on the account's initials badge. */
    readonly accentColor?: string;
    readonly enabled: boolean;
    readonly isDefault: boolean;
    readonly supported: true;
}
export interface UnsupportedProviderInstanceOption {
    readonly instanceId: ProviderInstanceId;
    readonly driver: ProviderDriverKind;
    readonly label: string;
    readonly enabled: boolean;
    readonly isDefault: false;
    readonly supported: false;
}
export function getProviderInstanceOptions(_settings: unknown): ProviderInstanceOption[] { return [{ instanceId: "arkos", provider: "arkos", driver: "arkos", label: "Arkos Engine", enabled: true, isDefault: true, supported: true }]; }
export function getUnsupportedProviderInstanceOptions(_settings: unknown): UnsupportedProviderInstanceOption[] { return []; }
export function resolveDefaultProviderInstanceId(_settings: unknown, _provider: ProviderKind): ProviderInstanceId { return "arkos"; }
export function resolveSelectableProviderInstanceId(_settings: unknown, _provider: ProviderKind, _requested?: ProviderInstanceId | null): ProviderInstanceId { return "arkos"; }
export function getServerDisabledProviders(_settings: unknown): ProviderKind[] { return []; }
export function didProviderEnablementChange(_previous: unknown, _next: unknown): boolean { return false; }
/** Server settings that change which native commands a provider reports. */
export function didProviderCommandDiscoverySettingsChange(_previous: unknown, _next: unknown): boolean { return false; }
export function serverSettingsToAppSettings(settings: ServerSettingsView): Partial<AppSettings> {
    return {
        defaultThreadEnvMode: settings.defaultThreadEnvMode,
        githubInboxIncludeUpstreams: settings.githubInboxIncludeUpstreams,
        sidechatExpiry: settings.sidechatExpiry,
        enableAssistantStreaming: settings.enableAssistantStreaming,
        keepAwakeMode: settings.keepAwakeMode,
        lowerProviderProcessPriority: settings.lowerProviderProcessPriority,
        disabledProviders: getServerDisabledProviders(settings),
        providerInstances: settings.providerInstances,
        textGenerationProvider: settings.textGenerationModelSelection.provider,
        textGenerationProviderInstanceId: settings.textGenerationModelSelection.instanceId,
        textGenerationModel: settings.textGenerationModelSelection.model,
        sourceControlWritingStyle: settings.sourceControlWritingStyle,
        sourceControlCustomInstructions: settings.sourceControlCustomInstructions,
        onboardingCompletedAt: settings.onboardingCompletedAt ?? null,
    };
}
function hasOwn<Key extends keyof AppSettings>(patch: Partial<AppSettings>, key: Key): boolean {
    return Object.prototype.hasOwnProperty.call(patch, key);
}
function touchesProviderDiscoverySettings(_patch: Partial<AppSettings>): boolean { return false; }
function serverSettingValuesEqual(left: unknown, right: unknown): boolean {
    if (Array.isArray(left) && Array.isArray(right)) {
        return (left.length === right.length &&
            left.every((value, index) => serverSettingValuesEqual(value, right[index])));
    }
    if (left !== null &&
        right !== null &&
        typeof left === "object" &&
        typeof right === "object" &&
        !Array.isArray(left) &&
        !Array.isArray(right)) {
        const leftEntries = Object.entries(left);
        const rightRecord = right as Record<string, unknown>;
        return (leftEntries.length === Object.keys(rightRecord).length &&
            leftEntries.every(([key, value]) => Object.prototype.hasOwnProperty.call(rightRecord, key) &&
                serverSettingValuesEqual(value, rightRecord[key])));
    }
    return Object.is(left, right);
}
export function appSettingsPatchToServerSettingsPatch(patch: Partial<AppSettings>, _current?: Pick<ServerSettingsView, "providers">): ServerSettingsPatch {
    const result: Record<string, unknown> = {};
    for (const key of ["enableAssistantStreaming", "lowerProviderProcessPriority", "defaultThreadEnvMode", "githubInboxIncludeUpstreams", "sidechatExpiry", "sourceControlWritingStyle", "sourceControlCustomInstructions"] as const) {
        if (patch[key] !== undefined)
            result[key] = patch[key];
    }
    return result as ServerSettingsPatch;
}
function isServerSettingsPatchEmpty(patch: ServerSettingsPatch): boolean {
    return Object.keys(patch).length === 0;
}
export function buildInitialServerSettingsMigrationPatch(settings: AppSettings): ServerSettingsPatch { return appSettingsPatchToServerSettingsPatch(settings); }
// After the initial server migration, browser storage must never hold plaintext
// secrets: the server materializes sensitive values from the update patch and
// returns them redacted, so the locally persisted copy keeps only the markers.
export function redactProviderInstanceSecretsForClient(_instances: ProviderInstanceConfigMap): ProviderInstanceConfigMap { return {}; }
function redactAppSettingsSecretsForClient(settings: AppSettings): AppSettings {
    const redactedInstances = redactProviderInstanceSecretsForClient(settings.providerInstances);
    return redactedInstances === settings.providerInstances
        ? settings
        : { ...settings, providerInstances: redactedInstances };
}
export function normalizeStoredAppSettings(settings: AppSettings): AppSettings {
    return redactAppSettingsSecretsForClient({
        ...normalizeAppSettings(settings),
        // Provider enablement belongs to the connected server. Scrub legacy values
        // so a browser profile cannot project one server's shutdown state onto another.
        disabledProviders: [],
    });
}
export function applyLocalAppSettingsPatch(settings: AppSettings, patch: Partial<AppSettings>): AppSettings { return normalizeStoredAppSettings({ ...settings, ...patch }); }
export function normalizeInitialStoredAppSettingsForServerMigration(settings: AppSettings, migrationCompleted: boolean): AppSettings {
    const normalized = normalizeAppSettings(settings);
    return migrationCompleted ? normalizeStoredAppSettings(normalized) : normalized;
}
export function getCustomModelsForProvider(_settings: unknown, _provider: ProviderKind): readonly string[] { return []; }
export function getDefaultCustomModelsForProvider(_settings: unknown, _provider: ProviderKind): readonly string[] { return []; }
export function getCustomModelsByProvider(_settings: unknown): Record<ProviderKind, readonly string[]> { return { arkos: [] }; }
export function getCustomModelsForProviderInstance(_settings: unknown, _instance: Pick<ProviderInstanceOption, "instanceId" | "provider" | "isDefault">): readonly string[] { return []; }
export function getAppModelOptions(_provider: ProviderKind, _custom: readonly string[], _selected?: string | null): AppModelOption[] { return []; }
export function resolveAppModelSelection(provider: ProviderKind, customModels: Record<ProviderKind, readonly string[]>, selectedModel: string | null | undefined): string {
    const customModelsForProvider = customModels[provider];
    const options = getAppModelOptions(provider, customModelsForProvider, selectedModel);
    return (resolveSelectableModel(provider, selectedModel, options) ?? getDefaultModel(provider) ?? "");
}
export function getProviderStartOptions(_settings: unknown, _instanceId?: ProviderInstanceId | null): ProviderStartOptions | undefined { return undefined; }
/**
 * Layers `overlay` over `base` per provider and per option key: the overlay
 * wins only for the provider options it names, so a seeded routing overlay
 * (e.g. a group's worker routing) never wipes the user's own start options
 * for other providers — or the untouched keys of a provider it does name.
 */
export function mergeProviderStartOptions(_base: ProviderStartOptions | undefined, _overlay: ProviderStartOptions | undefined): ProviderStartOptions | undefined { return undefined; }
/**
 * Single source of truth for mapping the streaming preference onto the orchestration
 * delivery mode used when dispatching turns (composer, chat, Kanban, and Tasks share this).
 */
export function resolveAssistantDeliveryMode(settings: Pick<AppSettings, "enableAssistantStreaming">): AssistantDeliveryMode {
    return settings.enableAssistantStreaming ? "streaming" : "buffered";
}
/**
 * Resolves the dispatch mode for a composer submit. The preference applies only
 * while a turn is live; Ctrl/Cmd+Enter temporarily selects the opposite mode.
 */
export function resolveFollowUpDispatchMode(input: {
    behavior: FollowUpBehavior;
    hasLiveTurn: boolean;
    useOppositeBehavior?: boolean;
}): FollowUpBehavior {
    if (!input.hasLiveTurn) {
        return "queue";
    }
    if (!input.useOppositeBehavior) {
        return input.behavior;
    }
    return input.behavior === "queue" ? "steer" : "queue";
}
export function getCustomBinaryPathForProvider(_settings: unknown, _provider: ProviderKind): string { return ""; }
export function getCustomBinaryPathForProviderInstance(_settings: unknown, _provider: ProviderKind, _instanceId: ProviderInstanceId): string { return ""; }
let resolvedDefaultAppSettings: AppSettings | undefined;
function getResolvedDefaultAppSettings(): AppSettings {
    resolvedDefaultAppSettings ??= normalizeAppSettings({
        ...DEFAULT_APP_SETTINGS,
        ...serverSettingsToAppSettings(DEFAULT_SERVER_SETTINGS_VIEW),
    });
    return resolvedDefaultAppSettings;
}
// Every `useAppSettings` caller resolves the same two inputs (the stored settings and the
// server's), and there are dozens of callers mounted at once, several inside the chat
// alone. Resolving once per input pair saves those passes and hands every caller the same
// `settings` object, so memos keyed on it agree across components.
let resolvedAppSettings: {
    local: AppSettings;
    server: ServerSettingsView | undefined;
    settings: AppSettings;
} | undefined;
function resolveAppSettings(local: AppSettings, server: ServerSettingsView | undefined): AppSettings {
    if (resolvedAppSettings?.local === local && resolvedAppSettings.server === server) {
        return resolvedAppSettings.settings;
    }
    const settings = normalizeAppSettings({
        ...normalizeStoredAppSettings(local),
        ...(server ? serverSettingsToAppSettings(server) : {}),
    });
    resolvedAppSettings = { local, server, settings };
    return settings;
}
export function useAppSettings() {
    const queryClient = useQueryClient();
    const serverSettingsQuery = useQuery(serverSettingsQueryOptions());
    const [localSettings, setSettings] = useLocalStorage(APP_SETTINGS_STORAGE_KEY, DEFAULT_APP_SETTINGS, AppSettingsSchema);
    const normalizedStoredSettingsRef = useRef(false);
    const serverSettingsMutationQueueRef = useRef<Promise<void>>(Promise.resolve());
    const pendingServerSettingsMigrationPatchRef = useRef<ServerSettingsPatch | null>(null);
    const enqueueServerSettingsMutation = useCallback(<Result>(mutation: () => Promise<Result>): Promise<Result> => {
        const queued = serverSettingsMutationQueueRef.current.then(() => mutation(), () => mutation());
        serverSettingsMutationQueueRef.current = queued.then(() => undefined, () => undefined);
        return queued;
    }, []);
    const defaults = getResolvedDefaultAppSettings();
    const settings = resolveAppSettings(localSettings, serverSettingsQuery.data);
    useEffect(() => {
        if (normalizedStoredSettingsRef.current) {
            return;
        }
        normalizedStoredSettingsRef.current = true;
        setSettings((previous) => {
            const normalized = normalizeAppSettings(previous);
            const migrationCompleted = hasCompletedServerSettingsMigration();
            if (!migrationCompleted) {
                pendingServerSettingsMigrationPatchRef.current =
                    buildInitialServerSettingsMigrationPatch(normalized);
            }
            // Legacy localStorage may be the only remaining plaintext source until
            // the server confirms migration; redact it immediately after that write.
            return normalizeInitialStoredAppSettingsForServerMigration(normalized, migrationCompleted);
        });
    }, [setSettings]);
    useEffect(() => {
        if (!serverSettingsQuery.data || serverSettingsMigrationInFlight) {
            return;
        }
        if (hasCompletedServerSettingsMigration()) {
            return;
        }
        const migrationPatch = pendingServerSettingsMigrationPatchRef.current ??
            buildInitialServerSettingsMigrationPatch(localSettings);
        if (isServerSettingsPatchEmpty(migrationPatch)) {
            globalThis.localStorage?.setItem(SERVER_SETTINGS_MIGRATION_STORAGE_KEY, "1");
            pendingServerSettingsMigrationPatchRef.current = null;
            setSettings((previous) => normalizeStoredAppSettings(previous));
            return;
        }
        serverSettingsMigrationInFlight = true;
        void enqueueServerSettingsMutation(() => ensureNativeApi().server.updateSettings(migrationPatch))
            .then((nextSettings) => {
            queryClient.setQueryData(serverQueryKeys.settings(), nextSettings);
            globalThis.localStorage?.setItem(SERVER_SETTINGS_MIGRATION_STORAGE_KEY, "1");
            pendingServerSettingsMigrationPatchRef.current = null;
            // The server now owns the migrated secrets; drop the local plaintext.
            setSettings((previous) => normalizeStoredAppSettings(previous));
        })
            .catch(() => {
            void queryClient.invalidateQueries({
                queryKey: serverQueryKeys.settings(),
            });
        })
            .finally(() => {
            serverSettingsMigrationInFlight = false;
        });
    }, [
        enqueueServerSettingsMutation,
        localSettings,
        queryClient,
        serverSettingsQuery.data,
        setSettings,
    ]);
    const refreshProvidersAfterEnablementChange = async () => {
        const api = ensureNativeApi();
        await api.server
            .refreshProviders()
            .then((result) => reconcileServerProviderStatuses(queryClient, result.providers))
            .catch(() => queryClient.invalidateQueries({ queryKey: serverQueryKeys.config() }));
        await queryClient
            .invalidateQueries({ queryKey: providerDiscoveryQueryKeys.all })
            .catch(() => undefined);
        await invalidateProviderUsageQueries(queryClient).catch(() => undefined);
    };
    const updateSettingsAndWait = async (patch: Partial<AppSettings>): Promise<void> => {
        const providerInstancesBeforePatch = patch.providerInstances !== undefined ? localSettings.providerInstances : undefined;
        // The pending migration ref retains the one plaintext snapshot that still
        // needs to reach the server; browser state and storage stay redacted.
        setSettings((prev) => applyLocalAppSettingsPatch(prev, patch));
        await enqueueServerSettingsMutation(async () => {
            const currentServerSettings = queryClient.getQueryData<ServerSettingsView>(serverQueryKeys.settings()) ??
                serverSettingsQuery.data;
            const serverPatch = appSettingsPatchToServerSettingsPatch(patch, currentServerSettings);
            if (isServerSettingsPatchEmpty(serverPatch)) {
                return;
            }
            const api = ensureNativeApi();
            try {
                const nextSettings = await api.server.updateSettings(serverPatch);
                queryClient.setQueryData(serverQueryKeys.settings(), nextSettings);
                if (hasOwn(patch, "githubInboxIncludeUpstreams")) {
                    // The repository set changed, so the inbox lists (and the review badge) are stale.
                    await queryClient
                        .invalidateQueries({ queryKey: githubInboxQueryKeys.all })
                        .catch(() => undefined);
                }
                if (hasOwn(patch, "disabledProviders")) {
                    await refreshProvidersAfterEnablementChange();
                }
                else if (touchesProviderDiscoverySettings(patch)) {
                    await queryClient
                        .invalidateQueries({ queryKey: providerDiscoveryQueryKeys.all })
                        .catch(() => undefined);
                }
            }
            catch {
                if (providerInstancesBeforePatch !== undefined) {
                    setSettings((prev) => {
                        const restored = normalizeAppSettings({
                            ...prev,
                            providerInstances: providerInstancesBeforePatch,
                        });
                        return redactAppSettingsSecretsForClient(restored);
                    });
                }
                await queryClient
                    .invalidateQueries({ queryKey: serverQueryKeys.settings() })
                    .catch(() => undefined);
                if (touchesProviderDiscoverySettings(patch)) {
                    await queryClient
                        .invalidateQueries({ queryKey: providerDiscoveryQueryKeys.all })
                        .catch(() => undefined);
                }
            }
        });
    };
    const updateSettings = (patch: Partial<AppSettings>): void => {
        void updateSettingsAndWait(patch);
    };
    const resetSettings = async (): Promise<void> => {
        // "Restore defaults" resets preferences, not lifecycle markers: clearing the
        // onboarding completion timestamp would replay the first-run tour on the next launch.
        const { onboardingCompletedAt: _keepOnboardingCompletedAt, ...resettableDefaults } = defaults;
        setSettings((prev) => ({
            ...DEFAULT_APP_SETTINGS,
            onboardingCompletedAt: prev.onboardingCompletedAt,
        }));
        await enqueueServerSettingsMutation(async () => {
            const currentServerSettings = queryClient.getQueryData<ServerSettingsView>(serverQueryKeys.settings()) ??
                serverSettingsQuery.data;
            const serverPatch = appSettingsPatchToServerSettingsPatch(resettableDefaults, currentServerSettings);
            const providerSettingsChanged = Boolean(serverPatch.providers && Object.keys(serverPatch.providers).length > 0);
            if (isServerSettingsPatchEmpty(serverPatch)) {
                return;
            }
            try {
                const nextSettings = await ensureNativeApi().server.updateSettings(serverPatch);
                queryClient.setQueryData(serverQueryKeys.settings(), nextSettings);
                if (providerSettingsChanged) {
                    await refreshProvidersAfterEnablementChange();
                }
            }
            catch {
                await queryClient
                    .invalidateQueries({ queryKey: serverQueryKeys.settings() })
                    .catch(() => undefined);
                if (providerSettingsChanged) {
                    await queryClient
                        .invalidateQueries({ queryKey: providerDiscoveryQueryKeys.all })
                        .catch(() => undefined);
                }
            }
        });
    };
    return {
        settings,
        serverSettings: serverSettingsQuery.data,
        updateSettings,
        updateSettingsAndWait,
        resetSettings,
        defaults,
    } as const;
}
function normalizeAppSettings(settings: AppSettings): AppSettings {
    const { enableAppshots: legacyEnableAppshots, allowComputerControlInNewChats: legacyAllowComputerControlInNewChats, showStudioSection: legacyShowStudioSection, ...currentSettings } = settings;
    return {
        ...currentSettings,
        railUsageInstanceIds: settings.railUsageInstanceIds ?? settings.railUsageProviders,
        enableAppSnap: settings.enableAppSnap || legacyEnableAppshots === true,
        // Read the legacy Studio key once: it defaults to true, so only an explicit
        // `false` carries over onto the renamed Groups section.
        showGroupsSection: settings.showGroupsSection && legacyShowStudioSection !== false,
        computerControlEnabled: settings.computerControlEnabled || legacyAllowComputerControlInNewChats === true,
        uiDensity: normalizeUiDensityValue(settings.uiDensity),
        chatWidth: normalizeChatWidthModeValue(settings.chatWidth),
        agentCursorFillColor: normalizeCursorHexColor(settings.agentCursorFillColor),
        agentCursorRimColor: normalizeCursorHexColor(settings.agentCursorRimColor),
        chatFontSizePx: normalizeChatFontSizePx(settings.chatFontSizePx),
        terminalFontSizePx: normalizeTerminalFontSizePx(settings.terminalFontSizePx),
        terminalFontFamily: normalizeTerminalFontFamily(settings.terminalFontFamily),
        hiddenProviders: [],
        disabledProviders: [],
        providerOrder: ["arkos"],
        railItemOrder: normalizeRailItemOrder(settings.railItemOrder),
        hiddenRailItems: normalizeHiddenRailItems(settings.hiddenRailItems),
        hiddenModels: [],
    };
}
