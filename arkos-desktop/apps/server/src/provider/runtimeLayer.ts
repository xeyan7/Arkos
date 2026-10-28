import {Layer} from "effect";
import {ProviderServiceLive} from "./Layers/ProviderService";
import {ProviderDiscoveryServiceLive} from "./Layers/ProviderDiscoveryService";
import {ProviderAdapterRegistryLive} from "./Layers/ProviderAdapterRegistry";
import {ProviderSessionDirectoryLive} from "./Layers/ProviderSessionDirectory";
import {ProviderSessionRuntimeRepositoryLive} from "../persistence/Layers/ProviderSessionRuntime";
export function makeServerProviderLayer(_options?:unknown){return Layer.mergeAll(
 ProviderServiceLive,ProviderDiscoveryServiceLive,ProviderAdapterRegistryLive,
 ProviderSessionDirectoryLive.pipe(Layer.provide(ProviderSessionRuntimeRepositoryLive)),
);}
