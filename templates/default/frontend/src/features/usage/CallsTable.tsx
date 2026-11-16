import { Gear, Person, Sparkles, TriangleExclamation } from "@gravity-ui/icons";
import { useMemo, useState } from "react";
import { ago, dateTime, ms, perMillion, tokens, usd } from "../../lib/format";
import { formatJson, locateInputs } from "../../lib/highlight";
import { useCall, usePrompt } from "../../lib/hooks";
import type { LlmCall, LlmCallDetail } from "../../lib/types";
import { Chip, CodeBlock, CopyButton, Drawer, Empty, Skeleton } from "../../ui";

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
  // The prompt version's template tells which parts of the user message were inputs.
  const { data: prompt } = usePrompt(call?.request ? call.prompt_key : "");
  const inputs = useMemo(() => {
    const template = prompt?.versions.find((v) => v.version === call?.prompt_version)?.user_template;
    return template && call?.request ? locateInputs(template, call.request.user) : [];
  }, [prompt, call]);
  const response = useMemo(() => formatJson(call?.response), [call?.response]);
  return (
    <Drawer
      open={!!id}
      onOpenChange={(next) => !next && onClose()}
      title={call ? `${call.prompt_key} · ${call.model}` : "Call"}
      description={call ? dateTime(call.created_at) : undefined}
      actions={call && <CopyButton size="sm" tooltip="Copy call as JSON" text={() => callJson(call)} />}
      width="40rem"
    >
      {!call ? (
        <Skeleton className="h-40" />
      ) : (
        <div className="space-y-6">
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
          <section className="space-y-3">
            <h3 className="text-xs font-medium text-muted">Messages</h3>
            {call.error && <CodeBlock title="Error" icon={<TriangleExclamation />} tone="danger" text={call.error} />}
            {call.request ? (
              <>
                <CodeBlock title="System" icon={<Gear />} text={call.request.system} />
                <CodeBlock title="User" icon={<Person />} tone="info" text={call.request.user} marks={inputs} />
                {call.response !== null && (
                  <CodeBlock
                    title="Response"
                    icon={<Sparkles />}
                    tone="ok"
                    text={response ?? call.response}
                    badge={response && <Chip outline>JSON · formatted</Chip>}
                  />
                )}
              </>
            ) : (
              <p className="text-xs text-muted">
                Payloads aren’t stored. Set <code>APP_LOG_LLM_PAYLOADS=true</code> to keep prompts and outputs.
              </p>
            )}
          </section>
        </div>
      )}
    </Drawer>
  );
}

/** The call as one JSON document, for pasting into an issue or another tool. */
function callJson(call: LlmCallDetail): string {
  return JSON.stringify(
    {
      prompt: { key: call.prompt_key, version: call.prompt_version, digest: call.prompt_digest },
      provider: call.provider_name || call.provider_kind,
      model: call.model,
      status: call.status,
      error: call.error,
      created_at: call.created_at,
      latency_ms: call.latency_ms,
      usage: {
        input_tokens: call.input_tokens,
        output_tokens: call.output_tokens,
        cache_read_tokens: call.cache_read_tokens,
        cache_write_tokens: call.cache_write_tokens,
        cost_usd: call.cost_usd,
      },
      system: call.request?.system ?? null,
      user: call.request?.user ?? null,
      response: call.response,
    },
    null,
    2,
  );
}
