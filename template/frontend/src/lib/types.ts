/** `via` is "dashboard" for the cookie session, "api" for a bearer key. */
export type Session = { via: "dashboard" | "api"; csrf_token: string };

export type ProviderKind = "openai" | "anthropic" | "bedrock" | "google";

export type Provider = {
  id: string;
  name: string;
  kind: ProviderKind;
  protocol: "chat" | "responses";
  base_url: string;
  region: string;
  catalog_id: string;
  models: string[];
  enabled: boolean;
  revision: number;
  secret_configured: boolean;
  secret_hint: string;
  last_tested_at: string | null;
  last_test_ok: boolean | null;
  last_test_ms: number | null;
  last_test_message: string | null;
  updated_at: string;
};

/** A connection test loads the provider's model list (no tokens spent). */
export type ProbeResult = { ok: boolean; latency_ms: number; message: string; models?: string[] };

export type PromptVersion = {
  id: string;
  prompt_key: string;
  version: number;
  status: "draft" | "published" | "retired";
  system: string;
  user_template: string;
  variables: string[];
  note: string;
  source: "ui" | "file";
  digest: string;
  revision: number;
  created_at: string;
  published_at: string | null;
  call_count: number;
};

export type PromptSummary = {
  key: string;
  name: string;
  description: string;
  active_version_id: string | null;
  active_version: number | null;
  published_count: number;
  has_draft: boolean;
  /** Runs return validated JSON (schema in app/llm/outputs.py). */
  structured: boolean;
  revision: number;
  updated_at: string;
};

export type PromptDetail = PromptSummary & {
  versions: PromptVersion[];
  output_schema: Record<string, unknown> | null;
};

export type Rates = {
  catalog_id: string;
  model_id: string;
  input: number | null;
  output: number | null;
  cache_read: number | null;
  cache_write: number | null;
  source: string;
};

/** POST /runs and the payload of an llm.run job. Blank optionals = the model's defaults. */
export type RunInput = {
  prompt_key: string;
  variables: Record<string, string>;
  provider_id: string;
  model: string;
  prompt_version_id?: string;
  temperature?: number;
  max_tokens?: number;
  /** Extra tries for failures the provider never processed (rate limit, overload). Default 2. */
  retries?: number;
};

export type RunResult = {
  prompt: string;
  text: string;
  data: Record<string, unknown> | null;
  usage: { input_tokens: number; output_tokens: number; cache_read_tokens: number; cache_write_tokens: number; total_tokens: number };
  cost_usd: number | null;
  latency_ms: number;
  model: string;
  provider: string;
  prompt_version: number;
  prompt_digest: string;
  attempts: number;
  call_ids: string[];
};

export type CatalogModel = {
  catalog_id: string;
  model_id: string;
  name: string;
  input: number | null;
  output: number | null;
  cache_read: number | null;
  cache_write: number | null;
  context_limit: number | null;
  output_limit: number | null;
  reasoning: boolean;
  source: "models.dev" | "manual";
  updated_at: string;
};

export type ModelsResponse = {
  summary: { models: number; catalogs: number; updated_at: string | null };
  catalogs: { catalog_id: string; models: number }[];
  models: CatalogModel[];
};

export type UsageRow = { calls: number; cost_usd: number; tokens: number; errors: number; avg_latency_ms: number };

export type UsageSummary = {
  days: number;
  totals: {
    calls: number;
    errors: number;
    error_rate: number;
    input_tokens: number;
    output_tokens: number;
    cache_read_tokens: number;
    cost_usd: number;
    unpriced_calls: number;
    p50_latency_ms: number;
    p95_latency_ms: number;
  };
  by_day: (UsageRow & { day: string })[];
  by_model: (UsageRow & { model: string; provider_name: string })[];
  by_prompt: (UsageRow & { prompt_key: string })[];
};

export type LlmCall = {
  id: string;
  provider_name: string;
  provider_kind: string;
  model: string;
  prompt_key: string;
  prompt_version: number | null;
  status: "ok" | "error";
  error: string | null;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  cost_usd: number | null;
  latency_ms: number;
  source: string;
  job_id: string | null;
  created_at: string;
};

export type LlmCallDetail = LlmCall & {
  prompt_digest: string | null;
  pricing: Rates | null;
  request: { system: string; user: string } | null;
  response: string | null;
};

export type Health = {
  status: string;
  service: string;
  environment: string;
  database_ms: number;
  worker: { online: boolean; workers: number; queued: number; running: number };
};

export type Job = {
  id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed" | "interrupted" | "cancelled";
  payload: Record<string, unknown>;
  result: RunResult | null;
  created_by: string | null;
  error: string | null;
  attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};
