import { TrashBin } from "@gravity-ui/icons";
import { useState } from "react";
import { count, ms, percent, shortDay, tokens, usd } from "../../lib/format";
import { useCalls, useClearUsage, usePrompts, useUsage } from "../../lib/hooks";
import type { UsageSummary } from "../../lib/types";
import { BarChart, Button, Chip, ConfirmDialog, Meter, PageHeader, Panel, SectionHeader, Segmented, Select, Stat } from "../../ui";
import { CallsTable } from "./CallsTable";

type Metric = "cost" | "calls" | "tokens";
const RANGES = [
  { value: "7", label: "7d" },
  { value: "30", label: "30d" },
  { value: "90", label: "90d" },
] as const;

export function UsagePage() {
  const [days, setDays] = useState<"7" | "30" | "90">("30");
  const [metric, setMetric] = useState<Metric>("cost");
  const [clearing, setClearing] = useState(false);
  const clear = useClearUsage();
  const [prompt, setPrompt] = useState("");
  const [status, setStatus] = useState<"" | "ok" | "error">("");
  const usage = useUsage(Number(days));
  const calls = useCalls({ prompt, status });
  const prompts = usePrompts();
  const data = usage.data;
  const t = data?.totals;

  return (
    <>
      <PageHeader
        title="Usage"
        description="Every model request with tokens, cost and latency. Prices come from models.dev and are frozen on each call."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setClearing(true)}>
              <TrashBin /> Clear usage
            </Button>
            <Segmented aria-label="Range" value={days} onChange={setDays} options={[...RANGES]} />
          </div>
        }
      />
      <ConfirmDialog
        open={clearing}
        onOpenChange={setClearing}
        title="Clear all usage?"
        description="Deletes every recorded call — tokens, cost and saved payloads — for all time, not just this range. Prompts, providers and prices stay. This can't be undone."
        confirmLabel="Clear usage"
        destructive
        pending={clear.isPending}
        onConfirm={() => clear.mutate(undefined, { onSuccess: () => setClearing(false) })}
      />

      <div className="stagger grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Spend"
          loading={!t}
          value={usd(t?.cost_usd ?? 0)}
          hint={t?.unpriced_calls ? <Chip tone="warn">{t.unpriced_calls} unpriced</Chip> : `${days} days`}
        />
        <Stat label="Requests" loading={!t} value={count(t?.calls ?? 0)} hint={t ? `${percent(t.error_rate)} errors` : undefined} />
        <Stat
          label="Tokens"
          loading={!t}
          value={tokens((t?.input_tokens ?? 0) + (t?.output_tokens ?? 0))}
          hint={t ? `${tokens(t.input_tokens)} in · ${tokens(t.output_tokens)} out` : undefined}
        />
        <Stat label="Latency p95" loading={!t} value={ms(t?.p95_latency_ms ?? 0)} hint={t ? `p50 ${ms(t.p50_latency_ms)}` : undefined} />
      </div>

      <Panel
        className="mt-3"
        title="Daily"
        actions={
          <Segmented
            aria-label="Metric"
            value={metric}
            onChange={setMetric}
            options={[
              { value: "cost", label: "Cost" },
              { value: "calls", label: "Requests" },
              { value: "tokens", label: "Tokens" },
            ]}
          />
        }
        bodyClassName="px-4 pb-4 pt-3"
      >
        <DailyChart data={data} metric={metric} />
      </Panel>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <Breakdown
          title="By model"
          rows={(data?.by_model ?? []).map((r) => ({ key: `${r.provider_name}/${r.model}`, label: r.model, sub: r.provider_name, ...r }))}
        />
        <Breakdown title="By prompt" rows={(data?.by_prompt ?? []).map((r) => ({ key: r.prompt_key, label: r.prompt_key, ...r }))} />
      </div>

      <section className="mt-6">
        <SectionHeader
          title="Requests"
          actions={
            <>
              <div className="w-40">
                <Select
                  size="sm"
                  aria-label="Prompt"
                  value={prompt || "__all"}
                  onChange={(v) => setPrompt(v === "__all" ? "" : v)}
                  options={[{ value: "__all", label: "All prompts" }, ...(prompts.data ?? []).map((p) => ({ value: p.key, label: p.name }))]}
                />
              </div>
              <Segmented
                aria-label="Status"
                value={status || "all"}
                onChange={(v) => setStatus(v === "all" ? "" : (v as "ok" | "error"))}
                options={[
                  { value: "all", label: "All" },
                  { value: "ok", label: "OK" },
                  { value: "error", label: "Errors" },
                ]}
              />
            </>
          }
        />
        <Panel>
          <CallsTable calls={calls.data} loading={calls.isPending} />
        </Panel>
      </section>
    </>
  );
}

function DailyChart({ data, metric }: { data: UsageSummary | undefined; metric: Metric }) {
  const rows = data?.by_day ?? [];
  const pick = (r: UsageSummary["by_day"][number]) => (metric === "cost" ? r.cost_usd : metric === "calls" ? r.calls : r.tokens);
  const fmt = metric === "cost" ? (v: number) => usd(v) : metric === "calls" ? count : tokens;
  return (
    <BarChart
      height={180}
      format={fmt}
      data={rows.map((r) => ({
        key: r.day,
        label: shortDay(r.day),
        value: pick(r),
        hint: `${usd(r.cost_usd)} · ${count(r.calls)} req · ${tokens(r.tokens)} tok`,
      }))}
    />
  );
}

function Breakdown({
  title,
  rows,
}: {
  title: string;
  rows: { key: string; label: string; sub?: string; calls: number; cost_usd: number; tokens: number; avg_latency_ms: number }[];
}) {
  const max = Math.max(...rows.map((r) => r.cost_usd), 0);
  return (
    <Panel title={title}>
      {rows.length === 0 ? (
        <div className="px-4 py-10 text-center text-sm text-muted">Nothing in this range.</div>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((row) => (
            <li key={row.key} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 px-4 py-2.5">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{row.label}</div>
                {row.sub && <div className="truncate text-xs text-muted">{row.sub}</div>}
              </div>
              <div className="text-right text-sm tabular-nums">{usd(row.cost_usd)}</div>
              <Meter value={row.cost_usd} max={max} />
              <div className="text-right text-xs tabular-nums text-muted">
                {count(row.calls)} req · {ms(row.avg_latency_ms)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
