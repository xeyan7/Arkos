import { useEffect, useState } from "react";
import type { AppRouter } from "../router";

// Keep the first HTML paint and pending routes visually continuous. This must
// stay independent of the app shell so loading it cannot delay that shell.
export function BootSplash() {
  return (
    <div className="app-boot-splash" role="status" aria-label="Opening Arkos">
      <img
        className="app-boot-splash__icon app-boot-splash__icon--handoff"
        src="/arkos-logo.svg"
        alt=""
        draggable={false}
      />
    </div>
  );
}
// Before the router has its first match, it renders nothing (there is no
// Suspense boundary yet). Cover that phase as well as lazy-route loading.
export function RouterStartupSplash({ router }: { router: AppRouter }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const update = () => {
      if (router.state.matches.length > 0 && !router.state.isLoading) setReady(true);
    };
    const unsubscribe = router.subscribe("onResolved", update);
    update();
    return unsubscribe;
  }, [router]);
  return ready ? null : <BootSplash />;
}
