import { MutationCache, QueryClient } from "@tanstack/react-query";
import { ApiError, errorMessage } from "./api";
import { notify } from "./notify";

export const keys = {
  session: ["session"] as const,
  health: ["health"] as const,
  providers: ["providers"] as const,
  prompts: ["prompts"] as const,
  prompt: (key: string) => ["prompts", key] as const,
  models: (catalog: string, q: string) => ["models", catalog, q] as const,
  usage: (days: number) => ["usage", days] as const,
  calls: (filters: Record<string, string>) => ["calls", filters] as const,
  call: (id: string) => ["call", id] as const,
  jobs: ["jobs"] as const,
  settings: ["settings"] as const,
};

export const queryClient = new QueryClient({
  // Mutations surface their own errors unless they opt out with meta.silent.
  mutationCache: new MutationCache({
    onError: (error, _vars, _ctx, mutation) => {
      if (mutation.meta?.silent) return;
      if (error instanceof ApiError && error.status === 401) return;
      notify.error(errorMessage(error));
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 1,
    },
    mutations: { retry: false },
  },
});
