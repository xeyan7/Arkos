export const APP_BASE_NAME = "Arkos";
const isCanaryDesktop =
  typeof window !== "undefined" && window.location?.protocol === "arkos-canary:";
const isBetaDesktop = typeof window !== "undefined" && window.location?.protocol === "arkos-beta:";
export const APP_DISPLAY_NAME = isCanaryDesktop
  ? "Arkos Canary"
  : isBetaDesktop
    ? "Arkos Beta"
    : import.meta.env.DEV
      ? `${APP_BASE_NAME} (Dev)`
      : APP_BASE_NAME;
export const APP_VERSION = import.meta.env.APP_VERSION || "0.0.0";
