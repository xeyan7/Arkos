import { describe, expect, it } from "vitest";
import {
  normalizeRuntimeModeForProvider,
  providerSupportsAutoRuntimeMode,
  runtimeModeEscalatesPrivilege,
} from "./runtimeMode";

describe("runtime mode compatibility", () => {
  it("checks auto mode support for arkos", () => {
    expect(providerSupportsAutoRuntimeMode("arkos")).toBe(true);
  });

  it("normalizes runtime modes for arkos", () => {
    expect(normalizeRuntimeModeForProvider("auto", "arkos")).toBe("auto");
    expect(normalizeRuntimeModeForProvider("approval-required", "arkos")).toBe("approval-required");
    expect(normalizeRuntimeModeForProvider("full-access", "arkos")).toBe("full-access");
  });

  it("treats Auto as more privileged than Supervised but less privileged than Full access", () => {
    expect(runtimeModeEscalatesPrivilege("approval-required", "auto")).toBe(true);
    expect(runtimeModeEscalatesPrivilege("auto", "full-access")).toBe(true);
    expect(runtimeModeEscalatesPrivilege("auto", "approval-required")).toBe(false);
  });
});
