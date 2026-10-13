// FILE: desktopIdentity.ts
// Purpose: Defines the canonical desktop application identity across packaging and runtime.

export const ARKOS_DESKTOP_SCHEME = "arkos";
export const ARKOS_DESKTOP_ORIGIN = `${ARKOS_DESKTOP_SCHEME}://app`;
export const ARKOS_DESKTOP_ENTRY_URL = `${ARKOS_DESKTOP_ORIGIN}/index.html`;
export const ARKOS_DESKTOP_UPDATE_CHANNEL = "arkos";
export const ARKOS_PRODUCTION_BUNDLE_ID = "com.xeyan7.arkos";
export const ARKOS_DEVELOPMENT_BUNDLE_ID = `${ARKOS_PRODUCTION_BUNDLE_ID}.dev`;
export const ARKOS_CANARY_BUNDLE_ID = `${ARKOS_PRODUCTION_BUNDLE_ID}.canary`;
/** Display/setup identity of the GUI host; this value does not confer native authority. */
export const ARKOS_DESKTOP_BUNDLE_ID_ENV = "ARKOS_DESKTOP_BUNDLE_ID";
export const ARKOS_CANARY_DESKTOP_SCHEME = "arkos-canary";
export const ARKOS_CANARY_DESKTOP_ORIGIN = `${ARKOS_CANARY_DESKTOP_SCHEME}://app`;
export const ARKOS_CANARY_DESKTOP_ENTRY_URL = `${ARKOS_CANARY_DESKTOP_ORIGIN}/index.html`;
export const ARKOS_CUA_BUNDLE_ID = `${ARKOS_PRODUCTION_BUNDLE_ID}.cua`;
export const ARKOS_CUA_DESKTOP_SCHEME = "arkos-cua";
export const ARKOS_CUA_DESKTOP_ORIGIN = `${ARKOS_CUA_DESKTOP_SCHEME}://app`;
export const ARKOS_CUA_DESKTOP_ENTRY_URL = `${ARKOS_CUA_DESKTOP_ORIGIN}/index.html`;
export const ARKOS_BETA_BUNDLE_ID = `${ARKOS_PRODUCTION_BUNDLE_ID}.beta`;
export const ARKOS_BETA_DESKTOP_SCHEME = "arkos-beta";
export const ARKOS_BETA_DESKTOP_ORIGIN = `${ARKOS_BETA_DESKTOP_SCHEME}://app`;
export const ARKOS_BETA_DESKTOP_ENTRY_URL = `${ARKOS_BETA_DESKTOP_ORIGIN}/index.html`;
export const ARKOS_SOURCE_DESKTOP_BUILD_MARKER = "arkos-source-desktop-build-v2";
export const ARKOS_DESKTOP_SMOKE_USER_DATA_ENV = "ARKOS_DESKTOP_SMOKE_USER_DATA";

export type ArkosDesktopFlavor = "production" | "development" | "canary" | "cua" | "beta";
export const ARKOS_PACKAGED_DESKTOP_FLAVORS = ["production", "canary", "cua", "beta"] as const;
export type ArkosPackagedDesktopFlavor = (typeof ARKOS_PACKAGED_DESKTOP_FLAVORS)[number];

/**
 * electron-updater matches the update channel against the release tag's
 * prerelease identifier, so the beta flavor must use the `beta` channel to see
 * `vX.Y.Z-beta.N` releases. Every other flavor keeps the `arkos` channel.
 */
export function desktopUpdateChannel(flavor: ArkosDesktopFlavor): string {
  return flavor === "beta" ? "beta" : ARKOS_DESKTOP_UPDATE_CHANNEL;
}

export interface ArkosDesktopIdentity {
  readonly flavor: ArkosDesktopFlavor;
  readonly displayName: string;
  readonly bundleId: string;
  readonly scheme: string;
  readonly origin: string;
  readonly entryUrl: string;
  readonly userDataDirectoryName: string;
  readonly defaultHomeDirectoryName: string;
  readonly usesScriptedUpdates: boolean;
}

export function resolveArkosDesktopFlavor(input: {
  readonly isDevelopment: boolean;
  readonly requestedFlavor?: string | undefined;
  readonly allowDevelopmentOverride?: boolean | undefined;
}): ArkosDesktopFlavor {
  const requestedFlavor = input.requestedFlavor?.trim().toLowerCase();
  if (requestedFlavor === "cua") {
    return "cua";
  }
  if (requestedFlavor === "canary") {
    return "canary";
  }
  if (requestedFlavor === "beta") {
    return "beta";
  }
  if (
    requestedFlavor === "development" &&
    (input.isDevelopment || input.allowDevelopmentOverride === true)
  ) {
    return "development";
  }
  return input.isDevelopment ? "development" : "production";
}

/** Packaged identity is fixed when the artifact is staged, before it is signed. */
export function resolveArkosDesktopRuntimeFlavor(input: {
  readonly isPackaged: boolean;
  readonly isDevelopment: boolean;
  readonly packagedFlavor?: unknown;
  readonly requestedFlavor?: string | undefined;
  readonly allowDevelopmentOverride?: boolean | undefined;
}): ArkosDesktopFlavor {
  if (input.isPackaged && input.packagedFlavor !== undefined) {
    const flavor = input.packagedFlavor;
    if (flavor === "production" || flavor === "canary" || flavor === "cua" || flavor === "beta") {
      return flavor;
    }
    throw new Error("The packaged Arkos desktop flavor is invalid. Rebuild the application.");
  }
  // Source launchers also use an app bundle on macOS. Their build marker keeps
  // the existing environment-based routing, while legacy packaged apps remain
  // Stable even when a developer shell happens to export a different flavor.
  if (input.isPackaged && input.allowDevelopmentOverride !== true) {
    return "production";
  }
  return resolveArkosDesktopFlavor(input);
}

export function canOverrideDesktopSmokeUserData(input: {
  readonly packagedFlavor?: unknown;
  readonly sourceBuildMarker?: string | undefined;
}): boolean {
  return (
    input.packagedFlavor === "cua" ||
    input.packagedFlavor === "beta" ||
    (input.packagedFlavor === undefined &&
      input.sourceBuildMarker === ARKOS_SOURCE_DESKTOP_BUILD_MARKER)
  );
}

export function arkosDesktopIdentity(flavor: ArkosDesktopFlavor): ArkosDesktopIdentity {
  if (flavor === "cua") {
    return {
      flavor,
      displayName: "Arkos Cua",
      bundleId: ARKOS_CUA_BUNDLE_ID,
      scheme: ARKOS_CUA_DESKTOP_SCHEME,
      origin: ARKOS_CUA_DESKTOP_ORIGIN,
      entryUrl: ARKOS_CUA_DESKTOP_ENTRY_URL,
      userDataDirectoryName: "arkos-cua",
      defaultHomeDirectoryName: ".arkos-cua",
      usesScriptedUpdates: true,
    };
  }
  if (flavor === "canary") {
    return {
      flavor,
      displayName: "Arkos Canary",
      bundleId: ARKOS_CANARY_BUNDLE_ID,
      scheme: ARKOS_CANARY_DESKTOP_SCHEME,
      origin: ARKOS_CANARY_DESKTOP_ORIGIN,
      entryUrl: ARKOS_CANARY_DESKTOP_ENTRY_URL,
      userDataDirectoryName: "arkos-canary",
      defaultHomeDirectoryName: ".arkos-canary",
      usesScriptedUpdates: true,
    };
  }
  if (flavor === "beta") {
    return {
      flavor,
      displayName: "Arkos Beta",
      bundleId: ARKOS_BETA_BUNDLE_ID,
      scheme: ARKOS_BETA_DESKTOP_SCHEME,
      origin: ARKOS_BETA_DESKTOP_ORIGIN,
      entryUrl: ARKOS_BETA_DESKTOP_ENTRY_URL,
      userDataDirectoryName: "arkos-beta",
      defaultHomeDirectoryName: ".arkos-beta",
      usesScriptedUpdates: false,
    };
  }
  if (flavor === "development") {
    return {
      flavor,
      displayName: "Arkos (Dev)",
      bundleId: ARKOS_DEVELOPMENT_BUNDLE_ID,
      scheme: ARKOS_DESKTOP_SCHEME,
      origin: ARKOS_DESKTOP_ORIGIN,
      entryUrl: ARKOS_DESKTOP_ENTRY_URL,
      userDataDirectoryName: "arkos-dev",
      defaultHomeDirectoryName: ".arkos-dev",
      usesScriptedUpdates: false,
    };
  }
  return {
    flavor,
    displayName: "Arkos",
    bundleId: ARKOS_PRODUCTION_BUNDLE_ID,
    scheme: ARKOS_DESKTOP_SCHEME,
    origin: ARKOS_DESKTOP_ORIGIN,
    entryUrl: ARKOS_DESKTOP_ENTRY_URL,
    userDataDirectoryName: "arkos",
    defaultHomeDirectoryName: ".arkos",
    usesScriptedUpdates: false,
  };
}
