import { Ellipsis, PlugConnection, Plus } from "@gravity-ui/icons";
import { useEffect, useRef, useState } from "react";
import { ago } from "../../lib/format";
import { useDeleteProvider, useProbe, useProviders, useSaveProvider, type ProviderInput } from "../../lib/hooks";
import type { Provider, ProviderKind } from "../../lib/types";
import {
  Button,
  Chip,
  cn,
  ConfirmDialog,
  Dialog,
  Dot,
  Empty,
  Field,
  Input,
  Menu,
  PageHeader,
  Panel,
  ScrollArea,
  Segmented,
  Skeleton,
  Switch,
} from "../../ui";

const KIND_LABEL: Record<ProviderKind, string> = {
  openai: "OpenAI-compatible",
  anthropic: "Anthropic",
  bedrock: "Amazon Bedrock",
  google: "Google Gemini",
};

// Bedrock Mantle is Bedrock's OpenAI-compatible endpoint (Bedrock API key, Chat
// Completions or Responses). It is stored as an "openai" provider pointed at
// bedrock-mantle.<region>.api.aws and shown here as a Bedrock API option.
const MANTLE_HOST = /^https:\/\/bedrock-mantle\.([a-z0-9-]+)\.api\.aws(?=\/|$)/;
const mantleUrl = (region: string) => `https://bedrock-mantle.${region || "us-east-1"}.api.aws/v1`;
const isMantle = (p: { kind: ProviderKind; base_url: string }) => p.kind === "openai" && MANTLE_HOST.test(p.base_url);

// Cloudflare Workers AI is OpenAI-compatible at a URL that carries the account id.
// It is stored as an "openai" provider and edited here by account id.
const WORKERS_AI_URL = /^https:\/\/api\.cloudflare\.com\/client\/v4\/accounts\/([0-9a-f]{32})\/ai\/v1$/i;
const workersAiUrl = (account: string) => `https://api.cloudflare.com/client/v4/accounts/${account.trim()}/ai/v1`;
const isWorkersAi = (p: { kind: ProviderKind; base_url: string }) => p.kind === "openai" && WORKERS_AI_URL.test(p.base_url);

type Preset = { id: string; label: string; form: Partial<Form> };
const PRESETS: Preset[] = [
  { id: "openai", label: "OpenAI", form: { kind: "openai", base_url: "", catalog_id: "openai" } },
  { id: "anthropic", label: "Anthropic", form: { kind: "anthropic", base_url: "", catalog_id: "anthropic" } },
  { id: "bedrock", label: "Bedrock", form: { kind: "bedrock", region: "us-east-1", catalog_id: "amazon-bedrock" } },
  { id: "google", label: "Gemini", form: { kind: "google", catalog_id: "google" } },
  { id: "workers-ai", label: "Workers AI", form: { kind: "cloudflare", catalog_id: "cloudflare-workers-ai" } },
  { id: "openrouter", label: "OpenRouter", form: { kind: "openai", base_url: "https://openrouter.ai/api/v1", catalog_id: "openrouter" } },
  { id: "ollama", label: "Ollama", form: { kind: "openai", base_url: "http://127.0.0.1:11434/v1", catalog_id: "" } },
];

type BedrockApi = "converse" | "mantle";
const CARD_MODELS = 8;

type Form = {
  name: string;
  /** "cloudflare" is Workers AI: saved as kind "openai" with the account's URL. */
  kind: ProviderKind | "cloudflare";
  /** Only for kind "bedrock": Converse (AWS credentials) or Mantle (OpenAI-compatible). */
  bedrock_api: BedrockApi;
  /** Only for kind "cloudflare": the account id in the Workers AI URL. */
  account_id: string;
  protocol: "chat" | "responses";
  base_url: string;
  region: string;
  catalog_id: string;
  /** Loaded from the provider ("Load models"), never typed in. */
  models: string[];
  enabled: boolean;
  api_key: string;
  aws_access_key_id: string;
  aws_secret_access_key: string;
};

const EMPTY: Form = {
  name: "OpenAI",
  kind: "openai",
  bedrock_api: "converse",
  account_id: "",
  protocol: "chat",
  base_url: "",
  region: "",
  catalog_id: "openai",
  models: [],
  enabled: true,
  api_key: "",
  aws_access_key_id: "",
  aws_secret_access_key: "",
};

/** Exactly the fields the API accepts (it rejects unknown keys). */
function toInput(form: Form): ProviderInput {
  const converse = form.kind === "bedrock" && form.bedrock_api === "converse";
  const mantle = form.kind === "bedrock" && form.bedrock_api === "mantle";
  return {
    name: form.name,
    kind: mantle || form.kind === "cloudflare" ? "openai" : form.kind,
    protocol: form.protocol,
    base_url: converse
      ? ""
      : form.kind === "cloudflare"
        ? workersAiUrl(form.account_id)
        : form.base_url.trim().replace(/\/+$/, ""),
    region: form.region,
    catalog_id: form.catalog_id,
    enabled: form.enabled,
    api_key: converse ? "" : form.api_key,
    aws_access_key_id: converse ? form.aws_access_key_id : "",
    aws_secret_access_key: converse ? form.aws_secret_access_key : "",
    models: form.models,
  };
}

function fromProvider(p: Provider): Form {
  const mantle = isMantle(p);
  return {
    ...EMPTY,
    name: p.name,
    kind: mantle ? "bedrock" : isWorkersAi(p) ? "cloudflare" : p.kind,
    bedrock_api: mantle ? "mantle" : "converse",
    account_id: p.base_url.match(WORKERS_AI_URL)?.[1] ?? "",
    protocol: p.protocol,
    base_url: p.base_url,
    region: p.region || (mantle ? (p.base_url.match(MANTLE_HOST)?.[1] ?? "") : ""),
    catalog_id: p.catalog_id,
    enabled: p.enabled,
    models: p.models,
  };
}

export function ProvidersPage() {
  const providers = useProviders();
  const [editing, setEditing] = useState<Provider | "new" | null>(null);
  return (
    <>
      <PageHeader
        title="Providers"
        description="Connections to model APIs. Keys are encrypted at rest (AES-256-GCM) and never sent back to the browser."
        actions={
          <Button variant="primary" onClick={() => setEditing("new")}>
            <Plus /> Add provider
          </Button>
        }
      />
      {providers.isPending ? (
        <Skeleton className="h-40" />
      ) : !providers.data?.length ? (
        <Panel>
          <Empty icon={<PlugConnection />} title="No providers yet" action={<Button onClick={() => setEditing("new")}>Add provider</Button>}>
            Connect OpenAI, Anthropic, Bedrock, Gemini, Workers AI — or any OpenAI-compatible endpoint like OpenRouter or
            Ollama.
          </Empty>
        </Panel>
      ) : (
        <div className="stagger grid gap-3 xl:grid-cols-2">
          {providers.data.map((p) => (
            <ProviderCard key={p.id} provider={p} onEdit={() => setEditing(p)} />
          ))}
        </div>
      )}
      {editing && <ProviderDialog provider={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function ProviderCard({ provider: p, onEdit }: { provider: Provider; onEdit: () => void }) {
  const probe = useProbe();
  const remove = useDeleteProvider();
  const [confirm, setConfirm] = useState(false);
  const test = () => probe.mutate({ ...toInput(fromProvider(p)), provider_id: p.id });
  // A new provider, or one whose endpoint changed (the API clears its last test),
  // tests itself once: that also loads its model list.
  const untested = p.enabled && p.last_test_ok === null;
  const autoTested = useRef(false);
  useEffect(() => {
    if (!untested || autoTested.current) return;
    autoTested.current = true;
    test();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per untested provider
  }, [untested]);
  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <span className={cn("text-sm font-semibold text-ink", !p.enabled && "text-muted")}>{p.name}</span>
          {!p.enabled && <Chip>disabled</Chip>}
        </span>
      }
      actions={
        <Menu
          trigger={
            <Button size="xs" variant="ghost" icon aria-label="Provider actions">
              <Ellipsis />
            </Button>
          }
          items={[
            { label: "Edit connection", onSelect: onEdit },
            { label: "Test & load models", onSelect: test },
            { separator: true },
            { label: "Delete", danger: true, onSelect: () => setConfirm(true) },
          ]}
        />
      }
      footer={
        <>
          <span className="flex min-w-0 items-center gap-1.5">
            {probe.isPending ? (
              <>
                <Dot tone="info" pulse /> Testing…
              </>
            ) : p.last_test_ok === null ? (
              <>
                <Dot /> Not tested
              </>
            ) : (
              <>
                <Dot tone={p.last_test_ok ? "ok" : "danger"} />
                <span className="truncate">
                  {p.last_test_ok ? `Connected · ${p.last_test_ms}ms` : "Failed"} · {ago(p.last_tested_at)}
                </span>
              </>
            )}
          </span>
          <Button size="xs" variant="ghost" pending={probe.isPending} onClick={test}>
            Load models
          </Button>
        </>
      }
      bodyClassName="p-4 space-y-3"
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
        <span className="font-medium text-ink-2">{isMantle(p) ? "Amazon Bedrock · Mantle" : isWorkersAi(p) ? "Cloudflare Workers AI" : KIND_LABEL[p.kind]}</span>
        {p.kind === "openai" && p.protocol === "responses" && <span>· Responses API</span>}
        {p.region && <span>· {p.region}</span>}
        <span>· prices from {p.catalog_id || "best match"}</span>
      </div>
      {p.base_url && <div className="mono truncate text-xs text-ink-2">{p.base_url}</div>}
      <div className="flex flex-wrap gap-1">
        {p.models.slice(0, CARD_MODELS).map((m) => (
          <Chip key={m} outline className="mono">
            {m}
          </Chip>
        ))}
        {p.models.length > CARD_MODELS && <Chip>+{p.models.length - CARD_MODELS} more</Chip>}
        {!p.models.length && <span className="text-xs text-muted">No models loaded yet</span>}
      </div>
      <div className="text-xs text-muted">
        {p.secret_configured ? (
          <>
            Key <span className="mono text-ink-2">{p.secret_hint}</span>
          </>
        ) : p.kind === "bedrock" ? (
          "Default AWS credential chain"
        ) : (
          "No key"
        )}
      </div>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={`Delete ${p.name}?`}
        description="Code that runs prompts on it by name will fail. Call history keeps the provider name."
        confirmLabel="Delete provider"
        destructive
        pending={remove.isPending}
        onConfirm={() => remove.mutate(p.id, { onSuccess: () => setConfirm(false) })}
      />
    </Panel>
  );
}

function ProviderDialog({ provider, onClose }: { provider: Provider | null; onClose: () => void }) {
  const [open, setOpen] = useState(true);
  const [preset, setPreset] = useState(provider ? "" : "openai");
  const [form, setForm] = useState<Form>(
    provider ? fromProvider(provider) : EMPTY,
  );
  const save = useSaveProvider();
  const probe = useProbe();
  const input = toInput(form);
  // A loaded model list belongs to the endpoint it came from.
  const set = <K extends keyof Form>(key: K, value: Form[K]) =>
    setForm((f) => ({ ...f, [key]: value, ...(key === "base_url" || key === "account_id" ? { models: [] } : {}) }));
  const loadModels = () =>
    probe.mutate(
      { ...input, provider_id: provider?.id },
      { onSuccess: (result) => result.ok && setForm((f) => ({ ...f, models: result.models ?? [] })) },
    );
  const mantle = form.kind === "bedrock" && form.bedrock_api === "mantle";
  const setBedrockApi = (api: BedrockApi) =>
    setForm((f) => ({
      ...f,
      bedrock_api: api,
      base_url: api === "mantle" ? (MANTLE_HOST.test(f.base_url) ? f.base_url : mantleUrl(f.region)) : "",
      protocol: "chat",
      models: [],
    }));
  const setRegion = (region: string) =>
    setForm((f) => ({
      ...f,
      region,
      models: [],
      // Mantle's URL carries the region; keep the two in step.
      base_url: f.bedrock_api === "mantle" ? f.base_url.replace(MANTLE_HOST, `https://bedrock-mantle.${region}.api.aws`) : f.base_url,
    }));
  const close = () => {
    setOpen(false);
    setTimeout(onClose, 200);
  };
  // The API sends a stored key only to the endpoint it was saved for.
  const endpointChanged = !!provider && (input.kind !== provider.kind || input.base_url !== provider.base_url);
  const keepHint = provider?.secret_configured
    ? endpointChanged
      ? "Re-enter the key — a stored key is only sent to the URL it was saved for"
      : `Leave blank to keep ${provider.secret_hint}`
    : undefined;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !next && close()}
      title={provider ? `Edit ${provider.name}` : "Add provider"}
      description="Credentials are tested from the API server, not your browser."
      width="34rem"
      footer={
        <>
          <Button className="mr-auto" pending={probe.isPending} onClick={loadModels}>
            Load models
          </Button>
          <Button onClick={close}>Cancel</Button>
          <Button
            variant="primary"
            pending={save.isPending}
            onClick={() => save.mutate({ ...input, id: provider?.id, revision: provider?.revision }, { onSuccess: close })}
          >
            {provider ? "Save" : "Add provider"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {!provider && (
          <div className="flex flex-wrap gap-1.5">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => {
                  setPreset(p.id);
                  setForm({ ...EMPTY, ...p.form, name: p.label } as Form);
                }}
                className={cn(
                  "h-7 rounded-md px-2.5 text-xs font-medium transition-all",
                  preset === p.id
                    ? "bg-surface text-ink shadow-[0_1px_2px_rgb(0_0_0/0.06),0_0_0_1px_var(--line-2)]"
                    : "text-muted hover:bg-surface-3 hover:text-ink",
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Name">
            <Input value={form.name} onChange={(e) => set("name", e.target.value)} />
          </Field>
          <Field label="Pricing catalog" hint="models.dev provider id">
            <Input className="mono" value={form.catalog_id} placeholder="best match" onChange={(e) => set("catalog_id", e.target.value)} />
          </Field>
          {form.kind === "openai" && (
            <>
              <Field label="Base URL" hint="Blank = api.openai.com" className="col-span-2">
                <Input className="mono" value={form.base_url} placeholder="https://api.openai.com/v1" onChange={(e) => set("base_url", e.target.value)} />
              </Field>
              <Field label="API" className="col-span-2">
                <Segmented
                  aria-label="Protocol"
                  value={form.protocol}
                  onChange={(v) => set("protocol", v)}
                  options={[
                    { value: "chat", label: "Chat Completions" },
                    { value: "responses", label: "Responses" },
                  ]}
                />
              </Field>
            </>
          )}
          {form.kind === "cloudflare" && (
            <>
              <Field label="Account ID" hint="Dashboard → Workers AI → REST API">
                <Input
                  className="mono"
                  value={form.account_id}
                  placeholder="32 hex characters"
                  onChange={(e) => set("account_id", e.target.value.trim())}
                />
              </Field>
              <Field label="Protocol" hint="Responses: gpt-oss models only">
                <Segmented
                  aria-label="Protocol"
                  value={form.protocol}
                  onChange={(v) => set("protocol", v)}
                  options={[
                    { value: "chat", label: "Chat" },
                    { value: "responses", label: "Responses" },
                  ]}
                />
              </Field>
            </>
          )}
          {form.kind === "anthropic" && (
            <Field label="Base URL" hint="Blank = api.anthropic.com" className="col-span-2">
              <Input className="mono" value={form.base_url} onChange={(e) => set("base_url", e.target.value)} />
            </Field>
          )}
          {form.kind === "bedrock" && (
            <Field label="API" className="col-span-2">
              <Segmented
                aria-label="Bedrock API"
                value={form.bedrock_api}
                onChange={setBedrockApi}
                options={[
                  { value: "converse", label: "Converse" },
                  { value: "mantle", label: "Mantle · OpenAI-compatible" },
                ]}
              />
            </Field>
          )}
          {mantle ? (
            <>
              <Field label="Region">
                <Input className="mono" value={form.region} onChange={(e) => setRegion(e.target.value)} />
              </Field>
              <Field label="Protocol">
                <Segmented
                  aria-label="Protocol"
                  value={form.protocol}
                  onChange={(v) => set("protocol", v)}
                  options={[
                    { value: "chat", label: "Chat" },
                    { value: "responses", label: "Responses" },
                  ]}
                />
              </Field>
              <Field label="Base URL" hint="Follows the region" className="col-span-2">
                <Input className="mono" value={form.base_url} onChange={(e) => set("base_url", e.target.value)} />
              </Field>
              <Field label="Bedrock API key" hint={keepHint ?? "Bedrock console → API keys"} className="col-span-2">
                <Input
                  type="password"
                  autoComplete="off"
                  className="mono"
                  value={form.api_key}
                  placeholder={provider?.secret_configured ? "••••••••" : "ABSK…"}
                  onChange={(e) => set("api_key", e.target.value)}
                />
              </Field>
            </>
          ) : form.kind === "bedrock" ? (
            <>
              <Field label="Region">
                <Input className="mono" value={form.region} onChange={(e) => setRegion(e.target.value)} />
              </Field>
              <div />
              <Field label="Access key id" hint={keepHint ?? "Blank = default AWS credential chain"}>
                <Input className="mono" value={form.aws_access_key_id} onChange={(e) => set("aws_access_key_id", e.target.value)} />
              </Field>
              <Field label="Secret access key">
                <Input type="password" className="mono" value={form.aws_secret_access_key} onChange={(e) => set("aws_secret_access_key", e.target.value)} />
              </Field>
            </>
          ) : (
            <Field
              label={form.kind === "cloudflare" ? "API token" : "API key"}
              hint={keepHint ?? (form.kind === "cloudflare" ? "Permissions: Workers AI Read + Edit" : undefined)}
              className="col-span-2"
            >
              <Input
                type="password"
                autoComplete="off"
                className="mono"
                value={form.api_key}
                placeholder={provider?.secret_configured ? "••••••••" : form.kind === "cloudflare" ? "Workers AI token" : "sk-…"}
                onChange={(e) => set("api_key", e.target.value)}
              />
            </Field>
          )}
          <Field
            label="Models"
            hint={form.models.length ? `${form.models.length} available · pick one when you run a prompt` : undefined}
            className="col-span-2"
          >
            {form.models.length ? (
              <ScrollArea className="max-h-28 rounded-lg bg-surface-2 shadow-[inset_0_0_0_1px_var(--line)]">
                <div className="flex flex-wrap gap-1 p-2">
                  {form.models.map((m) => (
                    <Chip key={m} outline className="mono">
                      {m}
                    </Chip>
                  ))}
                </div>
              </ScrollArea>
            ) : (
              <div className="rounded-lg px-3 py-2.5 text-xs text-muted shadow-[inset_0_0_0_1px_var(--line)]">
                Not loaded yet. <span className="font-medium text-ink-2">Load models</span> asks the provider what it serves
                and tests the connection — no tokens spent.
              </div>
            )}
          </Field>
        </div>
        <label className="flex items-center justify-between rounded-lg bg-surface-2 px-3 py-2.5 text-sm shadow-[inset_0_0_0_1px_var(--line)]">
          <span>Enabled</span>
          <Switch checked={form.enabled} onChange={(v) => set("enabled", v)} aria-label="Enabled" />
        </label>
        {probe.data && (
          <div className={cn("fade-up rounded-lg px-3 py-2 text-xs", probe.data.ok ? "bg-ok-soft text-ok-ink" : "bg-danger-soft text-danger-ink")}>
            {probe.data.message}
          </div>
        )}
      </div>
    </Dialog>
  );
}
