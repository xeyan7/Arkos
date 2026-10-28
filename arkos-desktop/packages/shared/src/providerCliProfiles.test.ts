import { describe, expect, it } from "vitest";
import { normalizeProviderCliAlias, providerCliCommandName } from "./providerCliProfiles";

describe("provider CLI profile names", () => {
  it("derives stable commands from instance ids rather than editable labels", () => {
    expect(providerCliCommandName({ provider: "arkos", instanceId: "arkos_custom" })).toBe("arkos-custom");
  });

  it("gives default instances explicit names without replacing bare commands", () => {
    expect(providerCliCommandName({ provider: "arkos", instanceId: "arkos" })).toBe("arkos-default");
  });

  it("accepts portable overrides and rejects shell syntax", () => {
    expect(
      providerCliCommandName({
        provider: "arkos",
        instanceId: "arkos_work",
        config: { cliAlias: "pairing-arkos" },
      }),
    ).toBe("pairing-arkos");
    expect(normalizeProviderCliAlias("arkos work")).toBeUndefined();
    expect(normalizeProviderCliAlias("arkos-work; rm -rf /")).toBeUndefined();
    expect(normalizeProviderCliAlias("arkos")).toBeUndefined();
  });
});
