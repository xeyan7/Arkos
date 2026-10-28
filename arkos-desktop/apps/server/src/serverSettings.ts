import {DEFAULT_SERVER_SETTINGS,ServerSettings,ServerSettingsError,ServerSettingsPatch,type ServerSettingsView} from "@arkos/contracts";
import {Deferred,Effect,FileSystem,Layer,PubSub,Ref,Schema,Semaphore,ServiceMap,Stream,type Scope} from "effect";
import {applyServerSettingsPatch} from "@arkos/shared/serverSettings";
import {ServerConfig} from "./config";
import {writeFileStringAtomically} from "./atomicWrite";
export interface ServerSettingsShape {
    readonly start: Effect.Effect<void, ServerSettingsError>;
    readonly ready: Effect.Effect<void, ServerSettingsError>;
    readonly getSettings: Effect.Effect<ServerSettings, ServerSettingsError>;
    readonly getSettingsView: Effect.Effect<ServerSettingsView, ServerSettingsError>;
    readonly getSnapshot: Effect.Effect<ServerSettingsSnapshot, ServerSettingsError>;
    readonly updateSettings: (patch: ServerSettingsPatch, 
    // Server-owned preparation may derive its patch inside the write lock.
    derivePatch?: (current: ServerSettings) => ServerSettingsPatch) => Effect.Effect<ServerSettings, ServerSettingsError>;
    readonly updateSettingsView: (patch: ServerSettingsPatch) => Effect.Effect<ServerSettingsView, ServerSettingsError>;
    /** Attach before returning so startup snapshot reads cannot race live updates. */
    readonly subscribeChanges: Effect.Effect<Stream.Stream<ServerSettings>, never, Scope.Scope>;
    readonly streamChanges: Stream.Stream<ServerSettings>;
    readonly streamViews: Stream.Stream<ServerSettingsView>;
}
export interface ServerSettingsSnapshot {
    readonly revision: number;
    readonly migrationVersion: number;
    readonly settings: ServerSettings;
}
export class ServerSettingsService extends ServiceMap.Service<ServerSettingsService, ServerSettingsShape>()("arkos/serverSettings/ServerSettingsService") {
    static readonly layerTest = (overrides: Partial<ServerSettings> = {}) => Layer.effect(ServerSettingsService, Effect.gen(function* () {
        const initialSettings = projectSettings({ ...DEFAULT_SERVER_SETTINGS, ...overrides });
        const currentSettingsRef = yield* Ref.make<ServerSettings>(initialSettings);
        const changesPubSub = yield* PubSub.unbounded<ServerSettings>();
        const revisionRef = yield* Ref.make(0);
        const emitChange = (settings: ServerSettings) => PubSub.publish(changesPubSub, settings).pipe(Effect.asVoid);
        const getSettings = Ref.get(currentSettingsRef);
        const updateSettings: ServerSettingsShape["updateSettings"] = (patch, derivePatch) =>
          Effect.gen(function* () {
            const currentSettings = yield* Ref.get(currentSettingsRef);
            const input = derivePatch?.(currentSettings) ?? patch;
            const next = projectSettings(applyServerSettingsPatch(currentSettings, input));
            yield* Ref.set(currentSettingsRef, next);
            yield* Ref.update(revisionRef, (r) => r + 1);
            yield* emitChange(next);
            return next;
          });
        return {
            start: Effect.void,
            ready: Effect.void,
            getSettings,
            getSettingsView: getSettings,
            getSnapshot: Effect.all({
                revision: Ref.get(revisionRef),
                settings: getSettings,
            }).pipe(Effect.map(({ revision, settings }) => ({
                revision,
                migrationVersion: SERVER_SETTINGS_MIGRATION_VERSION,
                settings,
            }))),
            updateSettings,
            updateSettingsView: (patch) => updateSettings(patch),
            subscribeChanges: PubSub.subscribe(changesPubSub).pipe(Effect.map((subscription) => Stream.fromSubscription(subscription))),
            get streamChanges() {
                return Stream.fromPubSub(changesPubSub);
            },
            get streamViews() {
                return Stream.fromPubSub(changesPubSub);
            },
        } satisfies ServerSettingsShape;
    }));
}
const SERVER_SETTINGS_MIGRATION_VERSION=4;
function projectSettings(settings:ServerSettings):ServerSettings{return {...settings,providers:DEFAULT_SERVER_SETTINGS.providers,providerInstances:{},textGenerationModelSelection:DEFAULT_SERVER_SETTINGS.textGenerationModelSelection};}
export function gateBetaOnlyProviders(settings:ServerSettings,_isEnabled?:(feature:string)=>boolean):ServerSettings{return projectSettings(settings);}
export function resolveTextGenerationProvider(settings:ServerSettings):ServerSettings{return projectSettings(settings);}
export function redactServerSettingsForClient(settings:ServerSettings):ServerSettings{return projectSettings(settings);}
export function toServerSettingsView(settings:ServerSettings):ServerSettingsView{return projectSettings(settings);}
const makeServerSettings=Effect.gen(function*(){
 const {settingsPath}=yield* ServerConfig;const fs=yield* FileSystem.FileSystem;
 const current=yield* Ref.make(DEFAULT_SERVER_SETTINGS);const revision=yield* Ref.make(0);
 const started=yield* Ref.make(false);const ready=yield* Deferred.make<void,ServerSettingsError>();
 const lock=yield* Semaphore.make(1);const changes=yield* PubSub.unbounded<ServerSettings>();
 const memory=settingsPath===":memory:";
 const error=(detail:string,cause:unknown)=>new ServerSettingsError({settingsPath,detail,cause});
 const readDisk=Effect.gen(function*(){
  if(memory)return {settings:yield* Ref.get(current),revision:yield* Ref.get(revision)};
  const exists=yield* fs.exists(settingsPath).pipe(Effect.mapError(cause=>error("Could not check settings file.",cause)));
  if(!exists)return {settings:DEFAULT_SERVER_SETTINGS,revision:0};
  const raw=yield* fs.readFileString(settingsPath).pipe(Effect.mapError(cause=>error("Could not read settings file.",cause)));
  return yield* Effect.try({try:()=>{const document:unknown=JSON.parse(raw);const record=document&&typeof document==="object"?document as Record<string,unknown>:{};
   return {settings:projectSettings(Schema.decodeUnknownSync(ServerSettings)(record.settings??record)),revision:typeof record.revision==="number"?record.revision:0};
  },catch:cause=>error("Could not decode settings file.",cause)});
 });
 const persist=(settings:ServerSettings,nextRevision:number)=>memory?Effect.void:writeFileStringAtomically({filePath:settingsPath,contents:JSON.stringify({settings,revision:nextRevision,migrationVersion:SERVER_SETTINGS_MIGRATION_VERSION},null,2)+"\n"}).pipe(Effect.mapError(cause=>error("Could not write settings file.",cause)));
 const start=Effect.gen(function*(){const first=yield* Ref.modify(started,value=>[!value,true]);if(!first)return yield* Deferred.await(ready);
  const startup=Effect.gen(function*(){const disk=yield* readDisk;yield* persist(disk.settings,disk.revision);yield* Ref.set(current,disk.settings);yield* Ref.set(revision,disk.revision);});
  const result=yield* Effect.exit(startup);yield* Deferred.done(ready,result);return yield* result;
 });
 const getSettings=Ref.get(current);
 const updateSettings:ServerSettingsShape["updateSettings"]=(patch,derivePatch)=>lock.withPermits(1)(Effect.gen(function*(){
  const disk=yield* readDisk;const input=derivePatch?.(disk.settings)??patch;
  const next=yield* Effect.try({try:()=>projectSettings(Schema.decodeUnknownSync(ServerSettings)(applyServerSettingsPatch(disk.settings,input))),catch:cause=>error("Could not apply settings.",cause)});
  const nextRevision=Math.max(disk.revision,yield* Ref.get(revision))+1;yield* persist(next,nextRevision);
  yield* Ref.set(current,next);yield* Ref.set(revision,nextRevision);yield* PubSub.publish(changes,next);return next;
 }));
 return {start,ready:Deferred.await(ready),getSettings,getSettingsView:getSettings,getSnapshot:Effect.all({settings:getSettings,revision:Ref.get(revision)}).pipe(Effect.map(snapshot=>({...snapshot,migrationVersion:SERVER_SETTINGS_MIGRATION_VERSION}))),updateSettings,
  updateSettingsView:(patch)=>updateSettings(patch),subscribeChanges:PubSub.subscribe(changes).pipe(Effect.map(subscription=>Stream.fromSubscription(subscription))),streamChanges:Stream.fromPubSub(changes),streamViews:Stream.fromPubSub(changes),
 } satisfies ServerSettingsShape;
});
export const ServerSettingsLive=Layer.effect(ServerSettingsService,makeServerSettings);
