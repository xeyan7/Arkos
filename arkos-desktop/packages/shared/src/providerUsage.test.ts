import { describe, expect, it } from "vitest";
import {
  providerUsageLabel,
  providerUsageDisplayName,
  providerUsageNeedsAuthDetail,
  selectVisibleProviderUsageSnapshots,
} from "./providerUsage";

describe("provider usage", () => {
  it("provides fallback label and display name", () => {
    expect(providerUsageLabel("arkos")).toBe("Usage");
    expect(providerUsageDisplayName("arkos")).toBe("Arkos");
    expect(providerUsageNeedsAuthDetail("arkos")).toBe("No agent runtime is connected.");
    expect(selectVisibleProviderUsageSnapshots([])).toEqual([]);
  });
});
