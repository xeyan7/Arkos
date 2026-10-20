import { useEffect } from "react";
import { useRouter } from "@tanstack/react-router";

/** Warms code-split route chunks once the browser is idle.
 *
 *  Settings and thread routes are reached through programmatic `navigate()`
 *  calls (sidebar gear, keyboard shortcut, the "New thread" button), so the
 *  router's intent-based preloading never fires for them — without this, the
 *  first open pays the chunk download/parse cost. For a brand-new thread that
 *  cost lands right on the draft-landing paint, so warming the thread chunk is
 *  the largest single lever for new-chat startup time.
 */
export function usePreloadRouteChunks() {
  const router = useRouter();

  useEffect(() => {
    // Let the shell paint before fetching the large chat graph. A root commit
    // can happen before first paint, particularly when a layout effect runs.
    let secondFrame: number | undefined;
    const firstFrame = requestAnimationFrame(() => {
      secondFrame = requestAnimationFrame(() => {
        router
          .preloadRoute({ to: "/$threadId", params: { threadId: "chunk-preload" } })
          .catch(() => {});
      });
    });

    const preloadSettings = () => {
      router.preloadRoute({ to: "/settings" }).catch(() => {
        // Preloading is best-effort; navigation falls back to loading on demand.
      });
    };

    // Idle callbacks can fire between network responses while the initial chat
    // is still loading. Do not let speculative settings imports compete with it.
    let idleCallbackId: number | undefined;
    let routeWaitId: ReturnType<typeof setTimeout> | undefined;
    const timeoutId = setTimeout(function waitForInitialRoute() {
      // A slow initial navigation may still be loading when this timer fires.
      // Speculative settings imports must not extend that navigation's delay.
      if (router.state.isLoading) {
        routeWaitId = setTimeout(waitForInitialRoute, 1_000);
        return;
      }
      if (typeof requestIdleCallback === "function") {
        idleCallbackId = requestIdleCallback(
          () => {
            if (router.state.isLoading) {
              routeWaitId = setTimeout(waitForInitialRoute, 1_000);
            } else preloadSettings();
          },
          { timeout: 5000 },
        );
      } else preloadSettings();
    }, 30_000);
    return () => {
      cancelAnimationFrame(firstFrame);
      if (secondFrame !== undefined) cancelAnimationFrame(secondFrame);
      clearTimeout(timeoutId);
      clearTimeout(routeWaitId);
      if (idleCallbackId !== undefined) cancelIdleCallback(idleCallbackId);
    };
  }, [router]);
}
