/** Query/mutation hooks. One place for keys, endpoints and cache updates. */
import { useMutation, useQuery } from "@tanstack/react-query";
import { useCallback, useRef } from "react";
import { flushSync } from "react-dom";
import { del, get, post, put } from "./api";
import { notify } from "./notify";
import { keys, queryClient } from "./query";
import { withTransition } from "./theme";
import type {
  Health,
  Job,
  LlmCall,
  LlmCallDetail,
  ModelsResponse,
  ProbeResult,
  PromptDetail,
  PromptSummary,
  PromptVersion,
  Provider,
  RunInput,
  RunResult,
  UsageSummary,
  WorkspaceSettings,
} from "./types";

// ── reads ───────────────────────────────────────────────────────────────────

export const useHealth = () => useQuery({ queryKey: keys.health, queryFn: () => get<Health>("/health") });
export const useProviders = () => useQuery({ queryKey: keys.providers, queryFn: () => get<Provider[]>("/providers") });
export const usePrompts = () => useQuery({ queryKey: keys.prompts, queryFn: () => get<PromptSummary[]>("/prompts") });
export const usePrompt = (key: string) =>
  useQuery({
    queryKey: keys.prompt(key),
    queryFn: () => get<PromptDetail>(`/prompts/${encodeURIComponent(key)}`),
    enabled: !!key,
  });
export const useUsage = (days: number) =>
  useQuery({
    queryKey: keys.usage(days),
    queryFn: () => get<UsageSummary>(`/usage/summary?days=${days}`),
    placeholderData: (previous) => previous,
  });
export const useCalls = (filters: { prompt?: string; status?: string; limit?: number }) => {
  const params = new URLSearchParams(
    Object.entries({ limit: "50", ...filters }).filter(([, v]) => v !== undefined && v !== "") as [string, string][],
  );
  return useQuery({
    queryKey: keys.calls(Object.fromEntries(params)),
    queryFn: () => get<LlmCall[]>(`/usage/calls?${params}`),
    placeholderData: (previous) => previous,
  });
};
export const useCall = (id: string | null) =>
  useQuery({ queryKey: keys.call(id ?? ""), queryFn: () => get<LlmCallDetail>(`/usage/calls/${id}`), enabled: !!id });
export const useModels = (catalog: string, q: string) =>
  useQuery({
    queryKey: keys.models(catalog, q),
    queryFn: () => get<ModelsResponse>(`/models?${new URLSearchParams({ catalog, q, limit: "200" })}`),
    placeholderData: (previous) => previous,
  });
export const useJobs = () =>
  useQuery({
    queryKey: keys.jobs,
    queryFn: () => get<{ worker: Health["worker"]; jobs: Job[] }>("/jobs"),
    refetchInterval: (query) =>
      query.state.data?.jobs.some((j) => j.status === "queued" || j.status === "running") ? 1500 : 15_000,
  });

// The last settings this browser saw, so the shell paints in the right layout before
// /settings answers. Only a hint: the server's copy wins.
const SETTINGS_HINT = "fstack-starter:settings";

function settingsHint(): WorkspaceSettings | undefined {
  try {
    const raw = localStorage.getItem(SETTINGS_HINT);
    return raw ? (JSON.parse(raw) as WorkspaceSettings) : undefined;
  } catch {
    return undefined;
  }
}

function rememberSettings(settings: WorkspaceSettings) {
  try {
    localStorage.setItem(SETTINGS_HINT, JSON.stringify(settings));
  } catch {
    /* private mode */
  }
}

export const useSettings = () =>
  useQuery({
    queryKey: keys.settings,
    queryFn: async () => {
      const settings = await get<WorkspaceSettings>("/settings");
      rememberSettings(settings);
      return settings;
    },
    placeholderData: settingsHint,
    staleTime: 60_000,
  });

// ── writes ──────────────────────────────────────────────────────────────────

/** Save workspace settings. The UI follows at once (cross-faded), and rolls back on error. */
export function useSaveSettings() {
  return useMutation({
    mutationFn: (body: Partial<WorkspaceSettings>) => put<WorkspaceSettings>("/settings", body),
    onMutate: async (body) => {
      await queryClient.cancelQueries({ queryKey: keys.settings });
      const previous = queryClient.getQueryData<WorkspaceSettings>(keys.settings);
      if (previous) {
        withTransition(() => flushSync(() => queryClient.setQueryData(keys.settings, { ...previous, ...body })));
      }
      return { previous };
    },
    onError: (_error, _body, context) => {
      if (context?.previous) queryClient.setQueryData(keys.settings, context.previous);
    },
    onSuccess: (settings) => {
      queryClient.setQueryData(keys.settings, settings);
      rememberSettings(settings);
      notify.success("Saved for everyone in this workspace");
    },
  });
}

export type ProviderInput = Omit<
  Provider,
  "id" | "revision" | "secret_configured" | "secret_hint" | "last_tested_at" | "last_test_ok" | "last_test_ms" | "last_test_message" | "updated_at"
> & { api_key?: string; aws_access_key_id?: string; aws_secret_access_key?: string };

const refreshConfig = () => void queryClient.invalidateQueries({ queryKey: keys.providers });

export function useSaveProvider() {
  return useMutation({
    mutationFn: ({ id, revision, ...body }: ProviderInput & { id?: string; revision?: number }) =>
      id ? put<Provider>(`/providers/${id}`, { ...body, revision }) : post<Provider>("/providers", body),
    onSuccess: (provider, vars) => {
      refreshConfig();
      void queryClient.invalidateQueries({ queryKey: ["models"] }); // its catalog's prices load on save
      notify.success(vars.id ? `Saved ${provider.name}` : `Added ${provider.name}`);
    },
  });
}

export function useDeleteProvider() {
  return useMutation({
    mutationFn: (id: string) => del(`/providers/${id}`),
    onSuccess: () => {
      refreshConfig();
      notify.success("Provider removed");
    },
  });
}

export function useProbe() {
  return useMutation({
    meta: { silent: true },
    mutationFn: (body: ProviderInput & { provider_id?: string; model?: string }) => post<ProbeResult>("/providers/probe", body),
    onSuccess: (result, vars) => {
      if (vars.provider_id) void queryClient.invalidateQueries({ queryKey: keys.providers });
      if (result.ok) notify.success(result.message);
      else notify.error(result.message);
    },
  });
}

/**
 * Run a prompt (POST /runs). The API already retries failures the provider never
 * processed (`retries`, default 2). On top of that:
 * - `stop()` aborts the request; the server then starts no new provider request or
 *   retry (one already sent finishes and is recorded — it may be billed);
 * - `retry()` sends the last input again;
 * - `stopped` is true when the last run ended because of `stop()`.
 */
export function useRun() {
  const controller = useRef<AbortController | null>(null);
  const last = useRef<RunInput | null>(null);
  const mutation = useMutation({
    meta: { silent: true },
    mutationFn: (body: RunInput) => {
      controller.current?.abort();
      const current = new AbortController();
      controller.current = current;
      last.current = body;
      return post<RunResult>("/runs", body, current.signal);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["usage"] });
      void queryClient.invalidateQueries({ queryKey: ["calls"] });
    },
  });
  const { mutate } = mutation;
  const stop = useCallback(() => controller.current?.abort(), []);
  const retry = useCallback(() => {
    if (last.current) mutate(last.current);
  }, [mutate]);
  const stopped = mutation.error instanceof DOMException && mutation.error.name === "AbortError";
  return { ...mutation, stop, retry, stopped };
}

export function useCancelJob() {
  return useMutation({
    mutationFn: (id: string) => post<Job>(`/jobs/${id}/cancel`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.jobs });
      notify.info("Job cancelled");
    },
  });
}

export function useRetryJob() {
  return useMutation({
    mutationFn: (id: string) => post<Job>(`/jobs/${id}/retry`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.jobs });
      notify.info("Queued again");
    },
  });
}

export function useClearUsage() {
  return useMutation({
    mutationFn: () => del<{ deleted: number }>("/usage/calls"),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["usage"] });
      void queryClient.invalidateQueries({ queryKey: ["calls"] });
      void queryClient.invalidateQueries({ queryKey: keys.prompts }); // per-version call counts
      notify.success(`Cleared ${result.deleted.toLocaleString()} calls`);
    },
  });
}

export function useDeletePrompt(key: string) {
  return useMutation({
    mutationFn: () => del(`/prompts/${encodeURIComponent(key)}`),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: keys.prompt(key) });
      void queryClient.invalidateQueries({ queryKey: keys.prompts, exact: true });
      notify.success(`Deleted ${key}`);
    },
  });
}

export function useEnqueue() {
  return useMutation({
    mutationFn: (body: { kind: string; payload: Record<string, unknown> }) => post<Job>("/jobs", body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.jobs });
      notify.info("Queued for the worker");
    },
  });
}

const setPrompt = (prompt: PromptDetail) => {
  queryClient.setQueryData(keys.prompt(prompt.key), prompt);
  void queryClient.invalidateQueries({ queryKey: keys.prompts, exact: true });
};

export function useCreatePrompt() {
  return useMutation({
    mutationFn: (body: { key: string; name: string; description: string; system: string; user_template: string }) =>
      post<PromptDetail>("/prompts", body),
    onSuccess: setPrompt,
  });
}

export function useStartDraft(key: string) {
  return useMutation({
    mutationFn: (fromVersionId?: string) => post<PromptDetail>(`/prompts/${key}/draft`, { from_version_id: fromVersionId ?? null }),
    onSuccess: setPrompt,
  });
}

export function useSaveDraft(key: string) {
  return useMutation({
    meta: { silent: true },
    mutationFn: (body: { system: string; user_template: string; note: string; revision: number }) =>
      put<PromptVersion>(`/prompts/${key}/draft`, body),
  });
}

export function useDiscardDraft(key: string) {
  return useMutation({
    mutationFn: () => del(`/prompts/${key}/draft`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: keys.prompt(key) }),
  });
}

export function usePublish(key: string) {
  return useMutation({
    mutationFn: (body: { revision: number; note: string; activate: boolean }) => post<PromptDetail>(`/prompts/${key}/draft/publish`, body),
    onSuccess: (prompt) => {
      setPrompt(prompt);
      const v = prompt.versions.find((x) => x.status === "published" && x.id === prompt.active_version_id);
      notify.success(v ? `Published v${v.version}` : "Published");
    },
  });
}

export function useActivate(key: string) {
  return useMutation({
    mutationFn: (versionId: string) => post<PromptDetail>(`/prompts/${key}/activate`, { version_id: versionId }),
    onSuccess: (prompt) => {
      setPrompt(prompt);
      const v = prompt.versions.find((x) => x.id === prompt.active_version_id);
      notify.success(`v${v?.version} is now active`);
    },
  });
}

export function useSyncPrices() {
  return useMutation({
    mutationFn: () => post<{ models: number; catalogs: number }>("/models/sync"),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["models"] });
      notify.success(`${result.models.toLocaleString()} models synced`);
    },
  });
}
