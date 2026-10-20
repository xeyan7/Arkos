import { createElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";

import { routeTree } from "./routeTree.gen";
import { StoreProvider } from "./store";
import { BootSplash } from "./components/BootSplash";

type RouterHistory = NonNullable<Parameters<typeof createRouter>[0]["history"]>;

export function getRouter(history: RouterHistory) {
  const queryClient = new QueryClient();

  return createRouter({
    routeTree,
    history,
    // Routes are auto-code-split and have no loaders, so intent preloading only
    // fetches the route chunk on link hover/touch — first navigation skips the
    // chunk download/parse wait.
    defaultPreload: "intent",
    // The default pending view is empty. React replaces the HTML logo before
    // lazy routes finish, exposing a blank window unless we provide one.
    defaultPendingComponent: BootSplash,
    defaultPendingMs: 0,
    defaultPendingMinMs: 0,
    context: {
      queryClient,
    },
    Wrap: ({ children }) =>
      createElement(
        QueryClientProvider,
        { client: queryClient },
        createElement(StoreProvider, null, children),
      ),
  });
}

export type AppRouter = ReturnType<typeof getRouter>;

declare module "@tanstack/react-router" {
  interface Register {
    router: AppRouter;
  }
}
