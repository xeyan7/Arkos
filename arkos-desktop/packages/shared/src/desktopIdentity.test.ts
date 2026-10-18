import { describe, expect, it } from "vitest";

import {
  desktopUpdateChannel,
  resolveArkosDesktopFlavor,
  resolveArkosDesktopRuntimeFlavor,
  canOverrideDesktopSmokeUserData,
  ARKOS_SOURCE_DESKTOP_BUILD_MARKER,
  ARKOS_BETA_BUNDLE_ID,
  ARKOS_BETA_DESKTOP_ENTRY_URL,
  ARKOS_BETA_DESKTOP_ORIGIN,
  ARKOS_CANARY_BUNDLE_ID,
  ARKOS_CANARY_DESKTOP_ENTRY_URL,
  ARKOS_CANARY_DESKTOP_ORIGIN,
  ARKOS_CUA_BUNDLE_ID,
  ARKOS_CUA_DESKTOP_ENTRY_URL,
  ARKOS_CUA_DESKTOP_ORIGIN,
  ARKOS_DESKTOP_ENTRY_URL,
  ARKOS_DESKTOP_ORIGIN,
  ARKOS_DESKTOP_UPDATE_CHANNEL,
  ARKOS_DEVELOPMENT_BUNDLE_ID,
  ARKOS_PRODUCTION_BUNDLE_ID,
  arkosDesktopIdentity,
} from "./desktopIdentity";

describe("desktopIdentity", () => {
  it("uses the exact canonical production and development bundle IDs", () => {
    expect(ARKOS_PRODUCTION_BUNDLE_ID).toBe("com.arkos.desktop");
    expect(ARKOS_DEVELOPMENT_BUNDLE_ID).toBe("com.arkos.desktop.dev");
    expect(arkosDesktopIdentity("production").bundleId).toBe(ARKOS_PRODUCTION_BUNDLE_ID);
    expect(arkosDesktopIdentity("development").bundleId).toBe(ARKOS_DEVELOPMENT_BUNDLE_ID);
  });

  it("uses the exact packaged renderer origin and entry URL", () => {
    expect(ARKOS_DESKTOP_ORIGIN).toBe("arkos://app");
    expect(ARKOS_DESKTOP_ENTRY_URL).toBe("arkos://app/index.html");
  });

  it("uses the isolated Arkos desktop update channel", () => {
    expect(ARKOS_DESKTOP_UPDATE_CHANNEL).toBe("arkos");
  });

  it("matches the beta update channel to prerelease tags and keeps arkos otherwise", () => {
    expect(desktopUpdateChannel("beta")).toBe("beta");
    expect(desktopUpdateChannel("production")).toBe(ARKOS_DESKTOP_UPDATE_CHANNEL);
    expect(desktopUpdateChannel("canary")).toBe(ARKOS_DESKTOP_UPDATE_CHANNEL);
    expect(desktopUpdateChannel("development")).toBe(ARKOS_DESKTOP_UPDATE_CHANNEL);
  });

  it("gives Canary a fully separate desktop identity and storage profile", () => {
    expect(ARKOS_CANARY_BUNDLE_ID).toBe("com.arkos.desktop.canary");
    expect(ARKOS_CANARY_DESKTOP_ORIGIN).toBe("arkos-canary://app");
    expect(ARKOS_CANARY_DESKTOP_ENTRY_URL).toBe("arkos-canary://app/index.html");
    expect(arkosDesktopIdentity("canary")).toEqual({
      flavor: "canary",
      displayName: "Arkos Canary",
      bundleId: ARKOS_CANARY_BUNDLE_ID,
      scheme: "arkos-canary",
      origin: ARKOS_CANARY_DESKTOP_ORIGIN,
      entryUrl: ARKOS_CANARY_DESKTOP_ENTRY_URL,
      userDataDirectoryName: "arkos-canary",
      defaultHomeDirectoryName: ".arkos-canary",
      usesScriptedUpdates: true,
    });
  });

  it("gives Cua a fully separate desktop identity and storage profile", () => {
    expect(ARKOS_CUA_BUNDLE_ID).toBe("com.arkos.desktop.cua");
    expect(ARKOS_CUA_DESKTOP_ORIGIN).toBe("arkos-cua://app");
    expect(ARKOS_CUA_DESKTOP_ENTRY_URL).toBe("arkos-cua://app/index.html");
    expect(arkosDesktopIdentity("cua")).toEqual({
      flavor: "cua",
      displayName: "Arkos Cua",
      bundleId: ARKOS_CUA_BUNDLE_ID,
      scheme: "arkos-cua",
      origin: ARKOS_CUA_DESKTOP_ORIGIN,
      entryUrl: ARKOS_CUA_DESKTOP_ENTRY_URL,
      userDataDirectoryName: "arkos-cua",
      defaultHomeDirectoryName: ".arkos-cua",
      usesScriptedUpdates: true,
    });
  });

  it("gives Beta a fully separate desktop identity and storage profile", () => {
    expect(ARKOS_BETA_BUNDLE_ID).toBe("com.arkos.desktop.beta");
    expect(ARKOS_BETA_DESKTOP_ORIGIN).toBe("arkos-beta://app");
    expect(ARKOS_BETA_DESKTOP_ENTRY_URL).toBe("arkos-beta://app/index.html");
    expect(arkosDesktopIdentity("beta")).toEqual({
      flavor: "beta",
      displayName: "Arkos Beta",
      bundleId: ARKOS_BETA_BUNDLE_ID,
      scheme: "arkos-beta",
      origin: ARKOS_BETA_DESKTOP_ORIGIN,
      entryUrl: ARKOS_BETA_DESKTOP_ENTRY_URL,
      userDataDirectoryName: "arkos-beta",
      defaultHomeDirectoryName: ".arkos-beta",
      usesScriptedUpdates: false,
    });
  });

  it("selects explicit source flavors without changing packaged Stable", () => {
    expect(resolveArkosDesktopFlavor({ isDevelopment: false })).toBe("production");
    expect(resolveArkosDesktopFlavor({ isDevelopment: true })).toBe("development");
    expect(
      resolveArkosDesktopFlavor({ isDevelopment: false, requestedFlavor: "development" }),
    ).toBe("production");
    expect(
      resolveArkosDesktopFlavor({
        isDevelopment: false,
        requestedFlavor: "development",
        allowDevelopmentOverride: true,
      }),
    ).toBe("development");
    expect(resolveArkosDesktopFlavor({ isDevelopment: false, requestedFlavor: " canary " })).toBe(
      "canary",
    );
    expect(resolveArkosDesktopFlavor({ isDevelopment: true, requestedFlavor: "canary" })).toBe(
      "canary",
    );
    expect(resolveArkosDesktopFlavor({ isDevelopment: false, requestedFlavor: "cua" })).toBe(
      "cua",
    );
    expect(resolveArkosDesktopFlavor({ isDevelopment: true, requestedFlavor: "CUA" })).toBe("cua");
    expect(resolveArkosDesktopFlavor({ isDevelopment: false, requestedFlavor: "beta" })).toBe(
      "beta",
    );
    expect(resolveArkosDesktopFlavor({ isDevelopment: false, requestedFlavor: " beta " })).toBe(
      "beta",
    );
    expect(resolveArkosDesktopFlavor({ isDevelopment: true, requestedFlavor: "beta" })).toBe(
      "beta",
    );
  });

  it("isolates development and Canary homes from packaged Stable", () => {
    expect(arkosDesktopIdentity("development").defaultHomeDirectoryName).toBe(".arkos-dev");
    expect(arkosDesktopIdentity("canary").defaultHomeDirectoryName).toBe(".arkos-canary");
    expect(arkosDesktopIdentity("cua").defaultHomeDirectoryName).toBe(".arkos-cua");
    expect(arkosDesktopIdentity("beta").defaultHomeDirectoryName).toBe(".arkos-beta");
    expect(arkosDesktopIdentity("production").defaultHomeDirectoryName).toBe(".arkos");
  });

  it.each(["production", "canary", "cua", "beta"] as const)(
    "uses the immutable %s package flavor despite inherited source settings",
    (packagedFlavor) => {
      expect(
        resolveArkosDesktopRuntimeFlavor({
          isPackaged: true,
          isDevelopment: true,
          packagedFlavor,
          requestedFlavor: "development",
          allowDevelopmentOverride: true,
        }),
      ).toBe(packagedFlavor);
    },
  );

  it("keeps legacy packaged Stable independent from a source shell's flavor", () => {
    expect(
      resolveArkosDesktopRuntimeFlavor({
        isPackaged: true,
        isDevelopment: false,
        requestedFlavor: "cua",
      }),
    ).toBe("production");
  });

  it("preserves source launcher routing, including its bundled macOS bootstrap", () => {
    expect(
      resolveArkosDesktopRuntimeFlavor({
        isPackaged: true,
        isDevelopment: false,
        requestedFlavor: "development",
        allowDevelopmentOverride: true,
      }),
    ).toBe("development");
    expect(
      resolveArkosDesktopRuntimeFlavor({
        isPackaged: false,
        isDevelopment: true,
        requestedFlavor: "canary",
      }),
    ).toBe("canary");
  });

  it.each(["development", "CUA", null])(
    "rejects malformed packaged identity %j before opening any profile",
    (packagedFlavor) => {
      expect(() =>
        resolveArkosDesktopRuntimeFlavor({
          isPackaged: true,
          isDevelopment: false,
          packagedFlavor,
        }),
      ).toThrow("packaged Arkos desktop flavor is invalid");
    },
  );

  it("isolates smoke profiles only for source launches or isolated packages", () => {
    expect(canOverrideDesktopSmokeUserData({ packagedFlavor: "cua" })).toBe(true);
    expect(canOverrideDesktopSmokeUserData({ packagedFlavor: "beta" })).toBe(true);
    expect(
      canOverrideDesktopSmokeUserData({
        sourceBuildMarker: ARKOS_SOURCE_DESKTOP_BUILD_MARKER,
      }),
    ).toBe(true);
    for (const packagedFlavor of ["production", "canary", "development", null]) {
      expect(
        canOverrideDesktopSmokeUserData({
          packagedFlavor,
          sourceBuildMarker: ARKOS_SOURCE_DESKTOP_BUILD_MARKER,
        }),
      ).toBe(false);
    }
    expect(canOverrideDesktopSmokeUserData({})).toBe(false);
  });
});
