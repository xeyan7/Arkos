import { describe, expect, it } from "vitest";
import { DEFAULT_MODEL, ENGINE_MODEL_CAPABILITIES } from "@arkos/contracts";
import {
  getDefaultModel,
  getModelCapabilities,
  getModelOptions,
  humanizeModelSlug,
  normalizeModelSlug,
  resolveModelSlug,
} from "./model";

describe("model helpers", () => {
  it("resolves default model for arkos", () => {
    expect(getDefaultModel("arkos")).toBe(DEFAULT_MODEL);
    expect(resolveModelSlug("anything", "arkos")).toBe(DEFAULT_MODEL);
    expect(normalizeModelSlug("custom", "arkos")).toBe(DEFAULT_MODEL);
  });

  it("humanizes model slug", () => {
    expect(humanizeModelSlug(DEFAULT_MODEL)).toBe("Engine configuration");
    expect(humanizeModelSlug("custom-model")).toBe("Custom Model");
  });

  it("retrieves model options and capabilities", () => {
    const options = getModelOptions("arkos");
    expect(options.length).toBeGreaterThan(0);
    expect(options[0]?.slug).toBe(DEFAULT_MODEL);
    expect(getModelCapabilities("arkos", DEFAULT_MODEL)).toEqual(ENGINE_MODEL_CAPABILITIES);
  });
});
