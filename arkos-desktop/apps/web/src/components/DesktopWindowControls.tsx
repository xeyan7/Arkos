import { useEffect, useState, type ReactNode } from "react";

import type { DesktopWindowState } from "@arkos/contracts";

import { useDesktopCustomTitleBarActive } from "~/hooks/useDesktopCustomTitleBar";
import { isElectron } from "~/env";
import { MinusIcon, XIcon } from "~/lib/icons";
import { cn } from "~/lib/utils";

import { CHAT_SURFACE_HEADER_HEIGHT_CLASS } from "./chat/chatHeaderControls";
import { toastManager } from "./ui/toast";

const DEFAULT_WINDOW_STATE: DesktopWindowState = {
  isMaximized: false,
  isFullscreen: false,
};

// Match the native Windows caption-button footprint: 46px wide, full top-bar
// height (CHAT_SURFACE_HEADER_HEIGHT_CLASS), flat (no radius/border), glyph centered. These are deliberately plain
// <button>s rather than the app's Button/Tooltip primitives — those inject a
// rounded "chrome" variant, conflicting size overrides, and a base-ui trigger that
// intercepts the click — so the chrome stays pixel-native and onClick routes
// straight to the window-control IPC.
const CAPTION_BUTTON_CLASS =
  "flex h-full w-[46px] shrink-0 items-center justify-center text-foreground outline-none focus-visible:outline-2 focus-visible:-outline-offset-4 focus-visible:outline-ring transition-colors duration-75 select-none hover:bg-foreground/[0.09] active:bg-foreground/[0.05] [-webkit-app-region:no-drag]";

// Windows close-button accent: red fill on hover with a white glyph.
const CLOSE_BUTTON_CLASS = "hover:bg-[#c42b1c] hover:text-white active:bg-[#b9281b]";

function reportWindowControlError(title: string, error: unknown): void {
  toastManager.add({
    type: "error",
    title,
    description: error instanceof Error ? error.message : "Please try again.",
  });
}

function CaptionSvg({ children }: { children: ReactNode }) {
  return (
    <span aria-hidden="true" className="flex size-3.5 items-center justify-center">
      {children}
    </span>
  );
}

export function DesktopWindowControls({ className }: { className?: string }) {
  const [windowState, setWindowState] = useState<DesktopWindowState>(DEFAULT_WINDOW_STATE);
  const customTitleBarActive = useDesktopCustomTitleBarActive();
  const controls = typeof window === "undefined" ? undefined : window.desktopBridge?.windowControls;

  useEffect(() => {
    if (!controls) return;
    let cancelled = false;

    void controls
      .getState()
      .then((state) => {
        if (!cancelled) setWindowState(state);
      })
      .catch((error: unknown) => {
        if (!cancelled) reportWindowControlError("Could not read window state", error);
      });
    const unsubscribe = controls.onState(setWindowState);

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [controls]);

  if (!isElectron || !customTitleBarActive || !controls) {
    return null;
  }

  const { isMaximized } = windowState;

  return (
    <div
      className={cn(
        "desktop-window-controls flex items-stretch [-webkit-app-region:no-drag]",
        CHAT_SURFACE_HEADER_HEIGHT_CLASS,
        className,
      )}
    >
      <button
        type="button"
        aria-label="Minimize"
        title="Minimize"
        className={CAPTION_BUTTON_CLASS}
        onClick={() => {
          void controls.minimize().catch((error: unknown) => {
            reportWindowControlError("Could not minimize window", error);
          });
        }}
      >
        <CaptionSvg>
          <MinusIcon className="size-3.5" />
        </CaptionSvg>
      </button>
      <button
        type="button"
        aria-label={isMaximized ? "Restore" : "Maximize"}
        title={isMaximized ? "Restore" : "Maximize"}
        className={CAPTION_BUTTON_CLASS}
        onClick={() => {
          void controls
            .toggleMaximize()
            .then(setWindowState)
            .catch((error: unknown) => {
              reportWindowControlError("Could not resize window", error);
            });
        }}
      >
        <CaptionSvg>
          <svg
            viewBox="0 0 16 16"
            className="size-3.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.25"
          >
            {isMaximized ? (
              <path d="M5.5 5.5v-3h8v8h-3m-8-5h8v8h-8z" />
            ) : (
              <rect x="3" y="3" width="10" height="10" />
            )}
          </svg>
        </CaptionSvg>
      </button>
      <button
        type="button"
        aria-label="Close"
        title="Close"
        className={cn(CAPTION_BUTTON_CLASS, CLOSE_BUTTON_CLASS)}
        onClick={() => {
          void controls.close().catch((error: unknown) => {
            reportWindowControlError("Could not close window", error);
          });
        }}
      >
        <CaptionSvg>
          <XIcon className="size-3.5" />
        </CaptionSvg>
      </button>
    </div>
  );
}
