import {DEFAULT_SERVER_SETTINGS,type ServerSettings,type ServerSettingsPatch,type ProviderStartOptions} from "@arkos/contracts";
import {deepMerge,type DeepPartial} from "./Struct";
export function applyServerSettingsPatch(current:ServerSettings,patch:ServerSettingsPatch):ServerSettings {
 const merged=deepMerge(current,patch as DeepPartial<ServerSettings>);
 return {...merged,providers:DEFAULT_SERVER_SETTINGS.providers,providerInstances:{},textGenerationModelSelection:DEFAULT_SERVER_SETTINGS.textGenerationModelSelection};
}
export function providerStartOptionsFromServerSettings(_settings:ServerSettings):ProviderStartOptions{return {};}
