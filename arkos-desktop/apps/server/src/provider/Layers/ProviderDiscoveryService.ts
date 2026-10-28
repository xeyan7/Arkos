import {Effect,Layer} from "effect";
import {ProviderDiscoveryService,type ProviderDiscoveryServiceShape} from "../Services/ProviderDiscoveryService";
import {ProviderUnsupportedError} from "../Errors";
export const ProviderDiscoveryServiceLive=Layer.succeed(ProviderDiscoveryService,{
 getComposerCapabilities:(input)=>Effect.succeed({provider:input.provider,supportsSkillMentions:false,supportsSkillDiscovery:false,supportsNativeSlashCommandDiscovery:false,supportsPluginMentions:false,supportsPluginDiscovery:false,supportsRuntimeModelList:false,supportsThreadCompaction:false,supportsThreadImport:false}),
 listCommands:()=>Effect.succeed({commands:[],source:"unavailable",cached:false}),listSkills:()=>Effect.succeed({skills:[],source:"unavailable",cached:false}),
 listPlugins:()=>Effect.succeed({marketplaces:[],marketplaceLoadErrors:[],remoteSyncError:null,featuredPluginIds:[],source:"unavailable",cached:false}),readPlugin:(input)=>Effect.fail(new ProviderUnsupportedError({provider:input.provider})),
 listModels:()=>Effect.succeed({models:[],source:"unavailable",cached:false}),listAgents:()=>Effect.succeed({agents:[],source:"unavailable",cached:false}),
} satisfies ProviderDiscoveryServiceShape);
