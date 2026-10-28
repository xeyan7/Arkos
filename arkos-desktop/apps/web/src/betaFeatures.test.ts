import { describe, expect, it } from "vitest";

import { PROVIDER_DESCRIPTORS } from "@arkos/shared/providerMetadata";
import { isBetaFeatureEnabled } from "@arkos/shared/betaFeatures";

import { visibleProviderDescriptors } from "./betaFeatures";

describe("visibleProviderDescriptors", () => {
  it("respects a disabled provider feature", () => {
    const visible = visibleProviderDescriptors((feature) => feature !== "arkos");
    expect(visible.some((d) => d.kind === "arkos")).toBe(false);
    expect(visible.map((d) => d.kind)).toEqual(
      PROVIDER_DESCRIPTORS.filter((d) => d.kind !== "arkos").map((d) => d.kind),
    );
  });

  it("offers Oh My Pi and the other providers in Stable", () => {
    const visible = visibleProviderDescriptors((feature) =>
      isBetaFeatureEnabled(feature, "production"),
    );
    expect(visible).toEqual(PROVIDER_DESCRIPTORS);
  });
});
