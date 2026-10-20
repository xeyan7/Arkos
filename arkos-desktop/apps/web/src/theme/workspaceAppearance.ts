import type { ChromeTheme, ThemeState } from "./theme.logic";

export const WORKSPACE_STYLE_REVISION = "sage-1";
export const WORKSPACE_UI_FONT = '"Segoe UI Variable", "Segoe UI", Arial, sans-serif';

export const WORKSPACE_CHROME_THEMES: Record<"light" | "dark", ChromeTheme> = {
  light: {
    accent: "#496a53",
    surface: "#f8f9f6",
    ink: "#26362d",
    contrast: 0,
    fonts: { ui: WORKSPACE_UI_FONT, code: null },
    opaqueWindows: true,
    semanticColors: { diffAdded: "#39764b", diffRemoved: "#b4483d", skill: "#89749a" },
  },
  dark: {
    accent: "#a3c5a4",
    surface: "#1c241e",
    ink: "#e4ede1",
    contrast: 0,
    fonts: { ui: WORKSPACE_UI_FONT, code: null },
    opaqueWindows: true,
    semanticColors: { diffAdded: "#8fc695", diffRemoved: "#e59a8d", skill: "#c4add8" },
  },
};

/** One-time adoption of the requested workspace appearance; keep editor preferences. */
export function migrateWorkspaceAppearance(state: ThemeState): ThemeState {
  return {
    ...state,
    mode: "light",
    systemUiFont: false,
    chromeThemes: {
      light: {
        ...WORKSPACE_CHROME_THEMES.light,
        fonts: {
          ...WORKSPACE_CHROME_THEMES.light.fonts,
          code: state.chromeThemes.light.fonts.code,
        },
      },
      dark: {
        ...WORKSPACE_CHROME_THEMES.dark,
        fonts: { ...WORKSPACE_CHROME_THEMES.dark.fonts, code: state.chromeThemes.dark.fonts.code },
      },
    },
  };
}

/** Additional material tokens shared by chat, settings, tools, dialogs, and pickers. */
export const WORKSPACE_LIGHT_VARIABLES: Record<string, string> = {
  "--background": "#f8f9f6",
  "--card": "#fffffd",
  "--popover": "#fffffd",
  "--primary": "#496a53",
  "--primary-foreground": "#ffffff",
  "--muted": "#eef2ea",
  "--muted-foreground": "#606c61",
  "--input": "#f1f4ec",
  "--border": "#d6dfd1",
  "--sidebar": "#e7ece7",
  "--sidebar-selected": "#ffffffa6",
  "--sidebar-accent": "#73877412",
  "--color-background-surface": "#f8f9f6",
  "--color-background-surface-under": "#f8f9f6",
  "--color-background-panel": "#fffffd",
  "--color-background-button-primary": "#496a53",
  "--color-background-button-primary-hover": "#3d5c46",
  "--color-background-button-primary-active": "#36513e",
  "--color-text-button-primary": "#ffffff",
  "--color-border": "#d6dfd1",
  "--app-content-surface": "#f8f9f6",
  "--app-settings-surface": "#f8f9f6",
  "--app-sidebar-surface": "#e7ece7",
  "--app-sidebar-chip-surface": "#e7ece7",
  "--app-overlay-surface": "#fffffd",
  "--app-composer-picker-surface": "#fffffd",
  "--composer-surface": "#fffffd",
  "--app-user-message-background": "#e8ede4",
};
