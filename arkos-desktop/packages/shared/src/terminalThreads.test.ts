import { describe, expect, it } from "vitest";
import {
  deriveTerminalProcessIdentity,
  isGenericTerminalThreadTitle,
  resolveTerminalVisualIdentity,
  terminalCliKindFromValue,
} from "./terminalThreads";

describe("terminalThreads", () => {
  it("recognizes generic terminal thread title", () => {
    expect(isGenericTerminalThreadTitle("New terminal")).toBe(true);
    expect(isGenericTerminalThreadTitle("Terminal 1")).toBe(false);
  });

  it("handles generic process commands", () => {
    expect(deriveTerminalProcessIdentity("npm test")).toMatchObject({
      cliKind: null,
      iconKey: "terminal",
      title: "npm test",
    });
  });

  it("resolves terminal visual identity", () => {
    expect(
      resolveTerminalVisualIdentity({
        cliKind: null,
        fallbackTitle: "Terminal 1",
      }),
    ).toMatchObject({
      cliKind: null,
      iconKey: "terminal",
      title: "Terminal 1",
    });
  });

  it("normalizes unknown cli kinds to null", () => {
    expect(terminalCliKindFromValue("unknown")).toBeNull();
  });
});
