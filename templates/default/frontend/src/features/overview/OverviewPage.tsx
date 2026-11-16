import { Link } from "react-router";
import { count, ms, percent, shortDay, usd } from "../../lib/format";
import { useCalls, useUsage } from "../../lib/hooks";
import { BarChart, buttonClass, PageHeader, Panel, SectionHeader, Stat } from "../../ui";
import { CallsTable } from "../usage/CallsTable";

export function OverviewPage() {
  const usage = useUsage(14);
  const calls = useCalls({ limit: 6 });
  const t = usage.data?.totals;
  return (
    <>
      <PageHeader
        title="Overview"
        description="Spend and requests at a glance. Everything here comes from the fstack_llm_calls log."
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

      <Panel
        className="mt-3"
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

      <section className="mt-6">
        <SectionHeader
          title="Latest requests"
          actions={
            <Link to="/usage" className="text-xs text-muted transition-colors hover:text-ink">
              View all →
            </Link>
          }
        />
        <Panel>
          <CallsTable calls={calls.data} loading={calls.isPending} compact />
        </Panel>
      </section>
    </>
  );
}
