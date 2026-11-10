import { ArrowRight, Check } from "@gravity-ui/icons";
import { Link } from "react-router";
import { count, ms, percent, shortDay, usd } from "../../lib/format";
import { useCalls, useHealth, useModels, useProviders, useUsage } from "../../lib/hooks";
import { BarChart, buttonClass, Chip, cn, Dot, PageHeader, Panel, Stat } from "../../ui";
import { CallsTable } from "../usage/CallsTable";

export function OverviewPage() {
  const usage = useUsage(14);
  const calls = useCalls({ limit: 6 });
  const t = usage.data?.totals;
  return (
    <>
      <PageHeader
        title="Overview"
        description="Health, spend and setup at a glance. Everything here is driven by the same llm_calls log."
        actions={
          <Link to="/run" className={buttonClass({ variant: "primary" })}>
            Run a prompt
          </Link>
        }
      />
      <div className="stagger grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Spend · 14d" loading={!t} value={usd(t?.cost_usd ?? 0)} />
        <Stat label="Requests · 14d" loading={!t} value={count(t?.calls ?? 0)} />
        <Stat label="Error rate" loading={!t} value={percent(t?.error_rate ?? 0)} />
        <Stat label="Latency p95" loading={!t} value={ms(t?.p95_latency_ms ?? 0)} />
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Panel
          title="Spend"
          actions={
            <Link to="/usage" className="text-xs text-muted transition-colors hover:text-ink">
              Details →
            </Link>
          }
          bodyClassName="px-4 pb-4 pt-3"
        >
          <BarChart
            height={168}
            format={(v) => usd(v)}
            data={(usage.data?.by_day ?? []).map((d) => ({
              key: d.day,
              label: shortDay(d.day),
              value: d.cost_usd,
              hint: `${usd(d.cost_usd)} · ${count(d.calls)} req`,
            }))}
          />
        </Panel>
        <SetupChecklist />
      </div>

      <Panel
        className="mt-3"
        title="Latest requests"
        actions={
          <Link to="/usage" className="text-xs text-muted transition-colors hover:text-ink">
            View all →
          </Link>
        }
      >
        <CallsTable calls={calls.data} loading={calls.isPending} compact />
      </Panel>
    </>
  );
}

function SetupChecklist() {
  const providers = useProviders();
  const usage = useUsage(30);
  const models = useModels("", "");
  const health = useHealth();
  const steps = [
    {
      done: (providers.data ?? []).some((p) => p.enabled && p.secret_configured),
      label: "Connect a provider",
      hint: "OpenAI, Anthropic, Bedrock, Gemini or any OpenAI-compatible URL",
      to: "/configure/providers",
    },
    {
      done: (models.data?.summary.models ?? 0) > 0,
      label: "Sync model prices",
      hint: "From models.dev — powers cost tracking",
      to: "/configure/models",
    },
    {
      done: (usage.data?.totals.calls ?? 0) > 0,
      label: "Run a prompt",
      hint: "Pick a prompt, provider and model in Run",
      to: "/run",
    },
    {
      done: !!health.data?.worker.online,
      label: "Start the worker",
      hint: "uv run tasks.py worker — runs background jobs",
      to: null,
    },
  ];
  const remaining = steps.filter((s) => !s.done).length;
  return (
    <Panel
      title="Setup"
      actions={remaining ? <Chip tone="warn">{remaining} left</Chip> : <Chip tone="ok">Ready</Chip>}
    >
      <ol className="divide-y divide-line">
        {steps.map((step) => {
          const body = (
            <>
              <span
                className={cn(
                  "grid size-[18px] shrink-0 place-items-center rounded-full transition-colors duration-300 [&_svg]:size-3",
                  step.done ? "bg-ok text-white" : "shadow-[inset_0_0_0_1.5px_var(--line-3)]",
                )}
              >
                {step.done && <Check />}
              </span>
              <span className="min-w-0 flex-1">
                <span className={cn("block text-sm font-medium", step.done && "text-muted line-through decoration-line-3")}>
                  {step.label}
                </span>
                <span className="block truncate text-xs text-muted">{step.hint}</span>
              </span>
              {step.to && !step.done && <ArrowRight className="size-3.5 text-faint" />}
              {!step.to && <Dot tone={step.done ? "ok" : "neutral"} pulse={step.done} />}
            </>
          );
          return (
            <li key={step.label}>
              {step.to ? (
                <Link to={step.to} className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-surface-2">
                  {body}
                </Link>
              ) : (
                <div className="flex items-center gap-3 px-4 py-3">{body}</div>
              )}
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}
