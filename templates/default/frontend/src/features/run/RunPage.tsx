import { ArrowRotateLeft, Copy, Play, Square } from "@gravity-ui/icons";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { errorMessage } from "../../lib/api";
import { ms, tokens, usd } from "../../lib/format";
import { usePrompt, usePrompts, useProviders, useRun } from "../../lib/hooks";
import { notify } from "../../lib/notify";
import { play } from "../../lib/sound";
import type { RunInput } from "../../lib/types";
import { Button, buttonClass, Chip, Empty, Field, Input, Kbd, ModelPicker, Morph, PageHeader, Panel, Select, Skeleton, Textarea } from "../../ui";

/** What to run: everything a RunInput needs except the variables. Unset = model default. */
export type RunSettings = Omit<RunInput, "variables">;

// The last choices, so the next visit starts there (this browser only).
type Saved = { prompt: string; provider: string; model: string; temperature: string; maxTokens: string; retries: string };
const SAVED_KEY = "run.settings";
const EMPTY: Saved = { prompt: "", provider: "", model: "", temperature: "", maxTokens: "", retries: "" };
function readSaved(): Saved {
  try {
    const value = JSON.parse(localStorage.getItem(SAVED_KEY) ?? "null");
    if (value && typeof value === "object") return { ...EMPTY, ...value };
  } catch {
    // private window or blocked storage: start empty
  }
  return EMPTY;
}

/**
 * The project's run screen: pick the prompt, provider and model (temperature, max
 * output tokens and retries optional), fill the prompt's variables, run. Projects
 * replace the input and output with their own logic, keeping the same calls:
 *
 *   const run = useRun();
 *   run.mutate({ ...settings, variables });  // run.isPending, run.data, run.error
 *   run.stop();                               // Stop: no new provider request or retry
 *   run.retry();                              // run the last input again
 *
 * For long work, `useEnqueue()` queues `{ kind: "llm.run", payload: { ...settings, variables } }`;
 * `useCancelJob()` / `useRetryJob()` stop or re-run it.
 */
export function RunPage() {
  const [params, setParams] = useSearchParams();
  const prompts = usePrompts();
  const providers = useProviders();
  const [saved, setSaved] = useState<Saved>(readSaved);
  const [values, setValues] = useState<Record<string, string>>({});
  const run = useRun();

  const runnable = (prompts.data ?? []).filter((p) => p.active_version_id);
  const prompt =
    runnable.find((p) => p.key === params.get("prompt")) ?? runnable.find((p) => p.key === saved.prompt) ?? runnable[0];
  const enabled = (providers.data ?? []).filter((p) => p.enabled);
  const provider = enabled.find((p) => p.id === saved.provider) ?? enabled[0];
  const model = provider && provider.id === saved.provider ? saved.model : "";
  const tuned = saved.temperature !== "" || saved.maxTokens !== "" || saved.retries !== "";
  const detail = usePrompt(prompt?.key ?? "");
  const variables = detail.data?.versions.find((v) => v.id === detail.data?.active_version_id)?.variables ?? [];

  const settings: RunSettings | null =
    prompt && provider && model
      ? {
          prompt_key: prompt.key,
          provider_id: provider.id,
          model,
          ...(saved.temperature !== "" ? { temperature: Number(saved.temperature) } : {}),
          ...(saved.maxTokens !== "" ? { max_tokens: Number(saved.maxTokens) } : {}),
          ...(saved.retries !== "" ? { retries: Number(saved.retries) } : {}),
        }
      : null;

  useEffect(() => {
    try {
      localStorage.setItem(SAVED_KEY, JSON.stringify(saved));
    } catch {
      // not worth surfacing
    }
  }, [saved]);

  const update = (patch: Partial<Saved>) => setSaved((s) => ({ ...s, ...patch }));

  function submit() {
    if (!settings || run.isPending) return;
    const body: RunInput = { ...settings, variables: Object.fromEntries(variables.map((v) => [v, values[v] ?? ""])) };
    run.mutate(body, {
      onSuccess: () => play("success"),
      onError: (error) => {
        if (!(error instanceof DOMException)) play("error"); // a Stop isn't a failure
      },
    });
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit();
      if (e.key === "Escape" && run.isPending) run.stop();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (prompts.isPending || providers.isPending) return <Skeleton className="h-96" />;
  if (!runnable.length) {
    return (
      <Empty title="No published prompts yet" action={<Link to="/prompts" className={buttonClass({})}>Open prompts</Link>}>
        Write and publish one in Prompts, or drop a Markdown file in backend/prompts and seed it: uv run tasks.py seed.
      </Empty>
    );
  }
  if (!enabled.length) {
    return (
      <Empty title="No providers yet" action={<Link to="/configure/providers" className={buttonClass({})}>Add a provider</Link>}>
        Connect OpenAI, Anthropic, Bedrock, Gemini, Workers AI or any OpenAI-compatible endpoint first.
      </Empty>
    );
  }

  return (
    <>
      <PageHeader title="Run" description="Choose a prompt, a provider and a model, fill its input and run it. Temperature and max output tokens are optional." />
      <div className="grid items-start gap-3 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <Panel
          title="Settings"
          actions={settings ? <Chip tone="ok">ready</Chip> : <Chip tone="warn">pick a model</Chip>}
          bodyClassName="p-4 space-y-4"
        >
          <Field label="Prompt">
            <Select
              value={prompt?.key ?? ""}
              onChange={(key) => {
                update({ prompt: key });
                setParams({ prompt: key });
              }}
              options={runnable.map((p) => ({
                value: p.key,
                label: p.name,
                description: `v${p.active_version} · ${p.structured ? "JSON" : "text"}`,
              }))}
            />
          </Field>
          <Field label="Provider">
            <Select
              value={provider?.id ?? ""}
              onChange={(id) => update({ provider: id, model: "" })}
              options={enabled.map((p) => ({
                value: p.id,
                label: p.name,
                description: p.models.length ? `${p.models.length} models` : "no models loaded",
              }))}
            />
          </Field>
          <Field
            label="Model"
            hint={provider && !provider.models.length ? "No models loaded for this provider: type an id, or load them in Configure → Providers." : undefined}
          >
            <ModelPicker
              aria-label="Model"
              models={provider?.models ?? []}
              value={model}
              disabled={!provider}
              onChange={(next) => provider && update({ provider: provider.id, model: next })}
            />
          </Field>

          <details className="group rounded-lg bg-surface-2 px-3 py-2 shadow-[inset_0_0_0_1px_var(--line)]">
            <summary className="cursor-pointer list-none text-xs font-medium text-ink-2">
              <span className="inline-block transition-transform group-open:rotate-90">›</span> Advanced
              {tuned && <Chip tone="accent" className="ml-2">custom</Chip>}
            </summary>
            <div className="mt-3 grid grid-cols-2 gap-3 pb-1">
              <Field label="Temperature">
                <Input
                  type="number"
                  min={0}
                  max={2}
                  step={0.1}
                  placeholder="Model default"
                  value={saved.temperature}
                  onChange={(e) => update({ temperature: e.target.value })}
                />
              </Field>
              <Field label="Max output tokens">
                <Input
                  type="number"
                  min={1}
                  step={1}
                  placeholder="Model default"
                  value={saved.maxTokens}
                  onChange={(e) => update({ maxTokens: e.target.value })}
                />
              </Field>
              <Field label="Retries" hint="Rate limits and overload only">
                <Input
                  type="number"
                  min={0}
                  max={5}
                  step={1}
                  placeholder="2"
                  value={saved.retries}
                  onChange={(e) => update({ retries: e.target.value })}
                />
              </Field>
              <p className="col-span-2 text-xs text-muted">
                Blank temperature / max tokens = the model's own default; blank retries = 2. Timeouts are never retried: the
                provider may have run the request.
              </p>
            </div>
          </details>
        </Panel>

        <div className="space-y-3">
          <Panel title="Input" bodyClassName="p-4 space-y-4">
            {variables.length ? (
              variables.map((name) => (
                <Field key={name} label={<span className="mono">{name}</span>}>
                  <Textarea
                    rows={name === "text" ? 6 : 2}
                    value={values[name] ?? ""}
                    onChange={(e) => setValues((v) => ({ ...v, [name]: e.target.value }))}
                  />
                </Field>
              ))
            ) : (
              <p className="text-sm text-muted">This prompt takes no input.</p>
            )}
            <div className="flex items-center gap-2">
              {run.isPending ? (
                <Button variant="danger-soft" className="flex-1" onClick={run.stop}>
                  <Square /> Stop <Kbd>Esc</Kbd>
                </Button>
              ) : (
                <Button variant="primary" className="flex-1" disabled={!settings} onClick={submit}>
                  <Play /> Run <Kbd>⌘↵</Kbd>
                </Button>
              )}
              {run.isError && !run.isPending && (
                <Button onClick={run.retry}>
                  <ArrowRotateLeft /> Retry
                </Button>
              )}
            </div>
          </Panel>
          <Output run={run} />
        </div>
      </div>
    </>
  );
}

function Output({ run }: { run: ReturnType<typeof useRun> }) {
  const result = run.data;
  const text = result ? (result.data ? JSON.stringify(result.data, null, 2) : result.text) : "";
  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          Output
          {result && (
            <>
              <Chip>v{result.prompt_version}</Chip>
              <span className="mono truncate text-[11px] text-muted">{result.model}</span>
              {result.attempts > 1 && <Chip tone="warn">{result.attempts} attempts</Chip>}
            </>
          )}
        </span>
      }
      actions={
        result && (
          <Button
            size="xs"
            variant="ghost"
            onClick={() => {
              void navigator.clipboard.writeText(text);
              notify.success("Copied");
            }}
          >
            <Copy /> Copy
          </Button>
        )
      }
      footer={
        <div className="flex w-full flex-wrap items-center gap-x-5 gap-y-1 tabular-nums">
          <span>
            Latency <Morph className="text-ink">{result ? ms(result.latency_ms) : "—"}</Morph>
          </span>
          <span>
            Tokens <Morph className="text-ink">{result ? tokens(result.usage.total_tokens) : "—"}</Morph>
          </span>
          <span>
            Cost <Morph className="text-ink">{result ? (result.cost_usd === null ? "unpriced" : usd(result.cost_usd, { precise: true })) : "—"}</Morph>
          </span>
        </div>
      }
    >
      <div className="min-h-[14rem] p-4">
        {run.isPending ? (
          <div className="space-y-2.5">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-2/3" />
            <p className="pt-2 text-xs text-muted">Running… failures the provider never processed are retried automatically.</p>
          </div>
        ) : run.stopped ? (
          <div className="code fade-up">
            Stopped. No new provider request or retry was started; one already sent still finishes and shows up in Usage.
          </div>
        ) : run.isError ? (
          <div className="code !bg-danger-soft !text-danger-ink fade-up">{errorMessage(run.error)}</div>
        ) : result ? (
          <pre key={result.call_ids[0]} className="code fade-up !bg-transparent !p-0 !shadow-none text-[13px] text-ink">
            {text}
          </pre>
        ) : (
          <div className="grid h-[12rem] place-items-center text-center text-sm text-muted">Fill the input and run the prompt.</div>
        )}
      </div>
    </Panel>
  );
}
