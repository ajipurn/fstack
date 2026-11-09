import { createBrowserRouter, Navigate } from "react-router";
import { Root } from "./Root";

// Each feature is its own chunk; the shell and kit load first.
export const router = createBrowserRouter([
  {
    element: <Root />,
    hydrateFallbackElement: null,
    children: [
      { index: true, lazy: async () => ({ Component: (await import("../features/overview/OverviewPage")).OverviewPage }) },
      { path: "run", lazy: async () => ({ Component: (await import("../features/run/RunPage")).RunPage }) },
      { path: "prompts", lazy: async () => ({ Component: (await import("../features/prompts/PromptsPage")).PromptsPage }) },
      { path: "prompts/:key", lazy: async () => ({ Component: (await import("../features/prompts/PromptDetailPage")).PromptDetailPage }) },
      { path: "usage", lazy: async () => ({ Component: (await import("../features/usage/UsagePage")).UsagePage }) },
      {
        path: "configure",
        lazy: async () => ({ Component: (await import("../features/configure/ConfigureLayout")).ConfigureLayout }),
        children: [
          { index: true, element: <Navigate to="providers" replace /> },
          { path: "providers", lazy: async () => ({ Component: (await import("../features/configure/ProvidersPage")).ProvidersPage }) },
          { path: "models", lazy: async () => ({ Component: (await import("../features/configure/ModelsPage")).ModelsPage }) },
        ],
      },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
