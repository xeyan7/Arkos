import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "vitest-browser-react";

const fixture = vi.hoisted(() => ({
  remembered: true,
  navigate: vi.fn(),
  refresh: vi.fn(async () => false),
  wait: vi.fn(async () => {}),
  splitViewsById: {},
  threadIds: [],
}));

vi.mock("@tanstack/react-router", () => ({ useNavigate: () => fixture.navigate }));
vi.mock("../store", () => ({
  EMPTY_THREAD_IDS: fixture.threadIds,
  useStore: (select: (state: unknown) => unknown) =>
    select({ threadsHydrated: true, threadIds: fixture.threadIds }),
}));
vi.mock("../splitViewStore", () => ({
  useSplitViewStore: (select: (state: unknown) => unknown) =>
    select({ hasHydrated: true, splitViewsById: fixture.splitViewsById }),
}));
vi.mock("./Sidebar.uiState", () => ({
  readSidebarUiState: () => ({
    lastThreadRoute: fixture.remembered ? { threadId: "missing-saved-chat" } : null,
  }),
}));
vi.mock("../nativeApi", () => ({ readNativeApi: () => ({}) }));
vi.mock("../chatRouteRecovery", () => ({
  refreshEmptyRouteRestoreSnapshot: fixture.refresh,
  waitForEmptyRouteRestoreFallbackDelay: fixture.wait,
}));

import { RestoreOrCreateChatRoute } from "./RestoreOrCreateChatRoute";

beforeEach(() => {
  vi.clearAllMocks();
  fixture.remembered = true;
  fixture.wait.mockImplementation(async () => {});
});

afterEach(() => vi.restoreAllMocks());

describe("chat startup in development StrictMode", () => {
  it("opens a fresh chat after recovering an unavailable saved chat", async () => {
    const createFreshChat = vi.fn(async () => ({ ok: true as const, threadId: null }));
    await render(
      <StrictMode>
        <RestoreOrCreateChatRoute
          resolveRestoreRoute={() => null}
          createFreshChat={createFreshChat}
        />
      </StrictMode>,
    );

    await expect.poll(() => createFreshChat.mock.calls.length).toBe(1);
    expect(fixture.refresh).toHaveBeenCalledTimes(1);
  });

  it("opens a fresh chat on the first launch without a saved chat", async () => {
    fixture.remembered = false;
    const createFreshChat = vi.fn(async () => ({ ok: true as const, threadId: null }));
    await render(
      <StrictMode>
        <RestoreOrCreateChatRoute
          resolveRestoreRoute={() => null}
          createFreshChat={createFreshChat}
        />
      </StrictMode>,
    );

    await expect.poll(() => createFreshChat.mock.calls.length).toBe(1);
    expect(fixture.refresh).not.toHaveBeenCalled();
  });

  it("does not open a chat after leaving the startup route during recovery", async () => {
    let finishRecovery!: () => void;
    fixture.wait.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          finishRecovery = resolve;
        }),
    );
    const createFreshChat = vi.fn(async () => ({ ok: true as const, threadId: null }));
    const screen = await render(
      <StrictMode>
        <RestoreOrCreateChatRoute
          resolveRestoreRoute={() => null}
          createFreshChat={createFreshChat}
        />
      </StrictMode>,
    );
    await expect.poll(() => fixture.refresh.mock.calls.length).toBe(1);
    await screen.unmount();
    finishRecovery();
    await Promise.resolve();
    expect(createFreshChat).not.toHaveBeenCalled();
  });
});
