import { useState } from "react";
import { ago, dateTime, ms, perMillion, tokens, usd } from "../../lib/format";
import { useCall } from "../../lib/hooks";
import type { LlmCall } from "../../lib/types";
import { Chip, Drawer, Empty, Skeleton } from "../../ui";

export function CallsTable({ calls, loading, compact }: { calls: LlmCall[] | undefined; loading?: boolean; compact?: boolean }) {
  const [open, setOpen] = useState<string | null>(null);
  if (loading && !calls) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-7" />
        ))}
      </div>
    );
  }
  if (!calls?.length) {
    return <Empty title="No calls yet">Run a prompt — every request lands here with tokens, cost and latency.</Empty>;
  }
  return (
    <>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Prompt</th>
              <th>Model</th>
              {!compact && <th>Provider</th>}
              <th className="num">Tokens</th>
              <th className="num">Cost</th>
              <th className="num">Latency</th>
              <th className="num">When</th>
            </tr>
          </thead>
          <tbody>
            {calls.map((call) => (
              <tr key={call.id} data-clickable="" onClick={() => setOpen(call.id)}>
                <td>
                  <div className="flex items-center gap-2">
                    <span className={call.status === "ok" ? "dot text-ok" : "dot text-danger"} />
                    <span className="font-medium">{call.prompt_key}</span>
                    <span className="text-xs text-muted">v{call.prompt_version}</span>
                    {call.source !== "api" && <Chip>{call.source}</Chip>}
                  </div>
                </td>
                <td className="max-w-[16rem] truncate">
                  <span className="mono text-xs text-ink-2">{call.model}</span>
                </td>
                {!compact && (
                  <td className="text-ink-2">{call.provider_name}</td>
                )}
                <td className="num text-ink-2">{tokens(call.input_tokens + call.output_tokens)}</td>
                <td className="num">{call.cost_usd === null ? <Chip tone="warn">unpriced</Chip> : usd(call.cost_usd, { precise: true })}</td>
                <td className="num text-ink-2">{ms(call.latency_ms)}</td>
                <td className="num whitespace-nowrap text-muted">{ago(call.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <CallDrawer id={open} onClose={() => setOpen(null)} />
    </>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5 text-sm">
      <span className="text-muted">{label}</span>
      <span className="min-w-0 truncate text-right">{children}</span>
    </div>
  );
}

function CallDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { data: call } = useCall(id);
  return (
    <Drawer
      open={!!id}
      onOpenChange={(next) => !next && onClose()}
      title={call ? `${call.prompt_key} · ${call.model}` : "Call"}
      description={call ? dateTime(call.created_at) : undefined}
      width="34rem"
    >
      {!call ? (
        <Skeleton className="h-40" />
      ) : (
        <div className="space-y-5">
          {call.error && <div className="code !bg-danger-soft !text-danger-ink">{call.error}</div>}
          <section>
            <h3 className="mb-1 text-xs font-medium text-muted">Request</h3>
            <div className="divide-y divide-line">
              <Row label="Status">
                <Chip tone={call.status === "ok" ? "ok" : "danger"}>{call.status}</Chip>
              </Row>
              <Row label="Provider">{call.provider_name || call.provider_kind}</Row>
              <Row label="Prompt">
                {call.prompt_key} v{call.prompt_version}{" "}
                <span className="mono text-xs text-muted">{call.prompt_digest?.slice(0, 10)}</span>
              </Row>
              <Row label="Latency">{ms(call.latency_ms)}</Row>
              <Row label="Source">{call.source}</Row>
            </div>
          </section>
          <section>
            <h3 className="mb-1 text-xs font-medium text-muted">Tokens & cost</h3>
            <div className="divide-y divide-line">
              <Row label="Input">{tokens(call.input_tokens)}</Row>
              <Row label="· cache read">{tokens(call.cache_read_tokens)}</Row>
              <Row label="· cache write">{tokens(call.cache_write_tokens)}</Row>
              <Row label="Output">{tokens(call.output_tokens)}</Row>
              <Row label="Cost">{call.cost_usd === null ? "unpriced" : usd(call.cost_usd, { precise: true })}</Row>
              {call.pricing && (
                <Row label="Rates /1M">
                  <span className="mono text-xs">
                    in {perMillion(call.pricing.input)} · out {perMillion(call.pricing.output)} · {call.pricing.catalog_id}
                  </span>
                </Row>
              )}
            </div>
          </section>
          {call.request ? (
            <>
              <section>
                <h3 className="mb-1.5 text-xs font-medium text-muted">System</h3>
                <pre className="code max-h-64 overflow-auto">{call.request.system || "—"}</pre>
              </section>
              <section>
                <h3 className="mb-1.5 text-xs font-medium text-muted">User</h3>
                <pre className="code max-h-64 overflow-auto">{call.request.user}</pre>
              </section>
              <section>
                <h3 className="mb-1.5 text-xs font-medium text-muted">Response</h3>
                <pre className="code max-h-80 overflow-auto">{call.response || "—"}</pre>
              </section>
            </>
          ) : (
            <p className="text-xs text-muted">
              Payloads aren’t stored. Set <code>APP_LOG_LLM_PAYLOADS=true</code> to keep prompts and outputs.
            </p>
          )}
        </div>
      )}
    </Drawer>
  );
}
