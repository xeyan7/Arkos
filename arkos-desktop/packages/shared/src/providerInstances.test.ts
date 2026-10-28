import { describe, expect, it } from "vitest";
import { DEFAULT_SERVER_SETTINGS } from "@arkos/contracts";
import {
  deriveProviderInstances,
  resolveProviderInstance,
  isProviderKind,
  defaultInstanceIdForProvider,
} from "./providerInstances";

describe("provider instance resolution", () => {
  it("resolves the default arkos instance", () => {
    const instances = deriveProviderInstances(DEFAULT_SERVER_SETTINGS);
    expect(instances).toHaveLength(1);
    expect(instances[0]?.instanceId).toBe("arkos");
    expect(instances[0]?.driver).toBe("arkos");
    expect(instances[0]?.enabled).toBe(true);
  });

  it("resolves provider instance by target", () => {
    const resolved = resolveProviderInstance(DEFAULT_SERVER_SETTINGS, {
      provider: "arkos",
      instanceId: "arkos",
    });
    expect(resolved).not.toBeNull();
    expect(resolved?.instanceId).toBe("arkos");
  });

  it("rejects unknown instance ids", () => {
    const resolved = resolveProviderInstance(DEFAULT_SERVER_SETTINGS, {
      instanceId: "unknown",
    });
    expect(resolved).toBeNull();
  });

  it("checks provider kind", () => {
    expect(isProviderKind("arkos")).toBe(true);
    expect(isProviderKind("claudeAgent")).toBe(false);
    expect(defaultInstanceIdForProvider("arkos")).toBe("arkos");
  });
});
