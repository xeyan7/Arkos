import { describe, expect, it } from "vitest";
import { DEFAULT_THEME_STATE, getCodeThemeSeed } from "./theme.logic";
import {
  migrateWorkspaceAppearance,
  WORKSPACE_CHROME_THEMES,
  WORKSPACE_UI_FONT,
} from "./workspaceAppearance";

describe("workspace appearance adoption", () => {
  it("adopts the green interface while retaining editor theme and code font choices", () => {
    const prior = {
      ...DEFAULT_THEME_STATE,
      mode: "dark" as const,
      codeThemeIds: { light: "github", dark: "nord" },
      chromeThemes: {
        light: { ...getCodeThemeSeed("github", "light"), fonts: { ui: "Inter", code: "Consolas" } },
        dark: {
          ...getCodeThemeSeed("nord", "dark"),
          fonts: { ui: "Inter", code: "JetBrains Mono" },
        },
      },
    };
    const result = migrateWorkspaceAppearance(prior);
    expect(result.mode).toBe("light");
    expect(result.chromeThemes.light.accent).toBe(WORKSPACE_CHROME_THEMES.light.accent);
    expect(result.chromeThemes.light.surface).toBe("#f8f9f6");
    expect(result.chromeThemes.light.fonts.ui).toBe(WORKSPACE_UI_FONT);
    expect(result.chromeThemes.light.fonts.code).toBe("Consolas");
    expect(result.chromeThemes.dark.fonts.code).toBe("JetBrains Mono");
    expect(result.codeThemeIds).toEqual(prior.codeThemeIds);
    expect(result.translucency).toEqual(prior.translucency);
    expect(prior.mode).toBe("dark");
  });
});
