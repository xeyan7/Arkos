import "../../index.css";

import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cdp, page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";

import {
  Sidebar,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
  SIDEBAR_OFFCANVAS_MOTION_CLASS,
  useSidebar,
} from "./sidebar";

function Controls({ name }: { name: string }) {
  const { state } = useSidebar();
  return (
    <>
      <SidebarTrigger aria-label={`Toggle ${name}`} />
      <output aria-label={`${name} state`}>{state}</output>
    </>
  );
}

function ControlledSidebar() {
  const [open, setOpen] = useState(true);
  return (
    <SidebarProvider open={open} onOpenChange={setOpen}>
      <Controls name="right" />
    </SidebarProvider>
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("sidebar toggles", () => {
  it("releases the global drag state when another control takes pointer capture", async () => {
    await page.viewport(1280, 800);
    const onResize = vi.fn();
    const screen = await render(
      <SidebarProvider defaultOpen>
        <Sidebar resizable={{ onResize }}>
          <SidebarRail />
        </Sidebar>
      </SidebarProvider>,
    );
    try {
      const rail = screen.container.querySelector<HTMLButtonElement>('[data-slot="sidebar-rail"]')!;
      const capture = vi.spyOn(rail, "setPointerCapture").mockImplementation(() => {});
      const x = rail.getBoundingClientRect().left;
      rail.dispatchEvent(
        new PointerEvent("pointerdown", { bubbles: true, pointerId: 1, button: 0, clientX: x }),
      );
      expect(document.body.style.cursor).toBe("col-resize");
      rail.dispatchEvent(new PointerEvent("lostpointercapture", { bubbles: true, pointerId: 1 }));
      expect(document.body.style.cursor).toBe("");
      expect(document.body.style.userSelect).toBe("");
      expect(onResize).toHaveBeenCalledTimes(1);
      capture.mockRestore();
    } finally {
      await screen.unmount();
    }
  });
  it("keeps collapsed offscreen controls out of the keyboard focus order", async () => {
    await page.viewport(1280, 800);
    const screen = await render(
      <SidebarProvider defaultOpen>
        <SidebarTrigger aria-label="Toggle focus panel" className="relative z-50" />
        <Sidebar>
          <input aria-label="Sidebar search" />
        </Sidebar>
        <input aria-label="Conversation composer" />
      </SidebarProvider>,
    );
    try {
      const toggle = page.getByRole("button", { name: "Toggle focus panel" });
      await toggle.click();
      const panel = screen.container.querySelector<HTMLElement>('[data-slot="sidebar-container"]')!;
      expect(panel.inert).toBe(true);
      await userEvent.tab();
      expect(document.activeElement).toBe(
        page.getByRole("textbox", { name: "Conversation composer" }).element(),
      );
      await toggle.click();
      expect(panel.inert).toBe(false);
      await userEvent.tab();
      expect(document.activeElement).toBe(
        page.getByRole("textbox", { name: "Sidebar search" }).element(),
      );
    } finally {
      await screen.unmount();
    }
  });
  it.each(["left", "right"] as const)(
    "settles the %s panel and layout gap immediately with reduced motion",
    async (side) => {
      const protocol = cdp() as {
        send(
          method: "Emulation.setEmulatedMedia",
          params: { features: { name: string; value: string }[] },
        ): Promise<void>;
      };
      await protocol.send("Emulation.setEmulatedMedia", {
        features: [{ name: "prefers-reduced-motion", value: "reduce" }],
      });
      await page.viewport(1280, 800);
      const screen = await render(
        <SidebarProvider defaultOpen>
          <SidebarTrigger aria-label="Toggle motion panel" className="relative z-50" />
          <Sidebar
            side={side}
            className={SIDEBAR_OFFCANVAS_MOTION_CLASS}
            gapClassName={SIDEBAR_OFFCANVAS_MOTION_CLASS}
          >
            Panel content
          </Sidebar>
        </SidebarProvider>,
      );
      try {
        const panel = screen.container.querySelector<HTMLElement>(
          '[data-slot="sidebar-container"]',
        )!;
        const gap = screen.container.querySelector<HTMLElement>('[data-slot="sidebar-gap"]')!;
        const initial = panel.getBoundingClientRect();
        await page.getByRole("button", { name: "Toggle motion panel" }).click();
        expect(panel.getAnimations()).toHaveLength(0);
        expect(gap.getAnimations()).toHaveLength(0);
        expect(panel.getBoundingClientRect().left).toBeCloseTo(
          initial.left + (side === "left" ? -initial.width : initial.width),
          0,
        );
        expect(gap.getBoundingClientRect().width).toBe(0);
        await page.getByRole("button", { name: "Toggle motion panel" }).click();
        expect(panel.getAnimations()).toHaveLength(0);
        expect(gap.getAnimations()).toHaveLength(0);
        expect(panel.getBoundingClientRect().left).toBeCloseTo(initial.left, 0);
        expect(gap.getBoundingClientRect().width).toBeCloseTo(initial.width, 0);
      } finally {
        await screen.unmount();
        await protocol.send("Emulation.setEmulatedMedia", { features: [] });
      }
    },
  );

  it.each(["missing", "rejecting"])(
    "toggles controlled and uncontrolled sidebars when CookieStore is %s",
    async (cookieStoreState) => {
      await page.viewport(1280, 800);
      vi.stubGlobal(
        "cookieStore",
        cookieStoreState === "missing"
          ? undefined
          : {
              set: () =>
                Promise.reject(
                  new TypeError("An unknown error occurred while writing the cookie."),
                ),
            },
      );
      const screen = await render(
        <>
          <SidebarProvider defaultOpen>
            <Controls name="left" />
          </SidebarProvider>
          <ControlledSidebar />
        </>,
      );
      try {
        for (const state of ["collapsed", "expanded"]) {
          for (const name of ["left", "right"]) {
            await page.getByRole("button", { name: `Toggle ${name}` }).click();
            await expect
              .element(page.getByRole("status", { name: `${name} state` }))
              .toHaveTextContent(state);
          }
        }
      } finally {
        await screen.unmount();
      }
    },
  );
});
