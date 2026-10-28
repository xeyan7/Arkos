import { DEFAULT_SERVER_SETTINGS } from "@arkos/contracts";
import { describe, expect, it } from "vitest";
import { applyServerSettingsPatch, providerStartOptionsFromServerSettings } from "./serverSettings";

describe("serverSettings", () => {
  it("applies patch while preserving engine defaults", () => {
    const updated = applyServerSettingsPatch(DEFAULT_SERVER_SETTINGS, {
      addProjectBaseDirectory: "/test/projects",
    });
    expect(updated.addProjectBaseDirectory).toBe("/test/projects");
  });

  it("returns default provider start options", () => {
    expect(providerStartOptionsFromServerSettings(DEFAULT_SERVER_SETTINGS)).toEqual({});
  });
});
