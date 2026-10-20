import { describe, expect, it } from "vitest";
import { resolveDesktopRendererMode } from "./desktopRendererMode";

const source = { isPackaged: false, isSourceDesktopBuild: true, devServerUrl: undefined, bundledRenderer: undefined };
describe("desktop renderer mode", () => {
  it("keeps the dev identity and profile when starting built UI without Vite", () => {
    expect(resolveDesktopRendererMode({ ...source, bundledRenderer: "1" })).toEqual({ isDevelopment: true, useBundledRenderer: true });
  });
  it("retains live development when a Vite URL is configured", () => {
    expect(resolveDesktopRendererMode({ ...source, devServerUrl: "http://localhost:5733" })).toEqual({ isDevelopment: true, useBundledRenderer: false });
  });
  it("does not let a normal installed app opt into development", () => {
    expect(resolveDesktopRendererMode({ ...source, isPackaged: true, isSourceDesktopBuild: false, devServerUrl: "http://localhost:5733", bundledRenderer: "1" })).toEqual({ isDevelopment: false, useBundledRenderer: false });
  });
  it("does not change source launches unless the mode is explicitly selected", () => {
    expect(resolveDesktopRendererMode(source)).toEqual({ isDevelopment: false, useBundledRenderer: false });
  });
});
