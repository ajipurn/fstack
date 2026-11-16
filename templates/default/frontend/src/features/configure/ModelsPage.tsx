import { ArrowsRotateRight, Magnifier } from "@gravity-ui/icons";
import { useDeferredValue, useState } from "react";
import { ago, perMillion, tokens } from "../../lib/format";
import { useModels, useSyncPrices } from "../../lib/hooks";
import { Button, Chip, cn, Empty, PageHeader, Panel, SectionHeader, Select, Skeleton } from "../../ui";

export function ModelsPage() {
  const [query, setQuery] = useState("");
  const [catalog, setCatalog] = useState("");
  const deferred = useDeferredValue(query);
  const models = useModels(catalog, deferred);
  const sync = useSyncPrices();
  const summary = models.data?.summary;

  return (
    <>
      <PageHeader
        title="Models & pricing"
        description={
          <>
            USD per 1M tokens from <a className="text-ink underline decoration-line-3 underline-offset-2" href="https://models.dev" target="_blank" rel="noreferrer">models.dev</a>.
            Each call stores the rate it was billed at, so refreshing never rewrites history.
          </>
        }
        actions={
          <Button pending={sync.isPending} onClick={() => sync.mutate()}>
            <ArrowsRotateRight /> Sync from models.dev
          </Button>
        }
      />
      <SectionHeader
        title="Catalog"
        meta={summary ? `${summary.models.toLocaleString()} models · ${summary.catalogs} catalogs · updated ${ago(summary.updated_at)}` : undefined}
        actions={
          <>
            <div className="w-44">
              <Select
                size="sm"
                aria-label="Catalog"
                value={catalog || "__all"}
                onChange={(v) => setCatalog(v === "__all" ? "" : v)}
                options={[
                  { value: "__all", label: "All catalogs" },
                  ...(models.data?.catalogs ?? []).map((c) => ({ value: c.catalog_id, label: c.catalog_id, description: `${c.models} models` })),
                ]}
              />
            </div>
            <label className="control control-sm w-56">
              <Magnifier className="size-3.5 text-faint" />
              <input className="control-inner" placeholder="Search models" value={query} onChange={(e) => setQuery(e.target.value)} />
            </label>
          </>
        }
      />
      <Panel>
        {models.isPending ? (
          <Skeleton className="m-4 h-48" />
        ) : !summary?.models ? (
          <Empty
            icon={<ArrowsRotateRight />}
            title="No prices yet"
            action={
              <Button variant="primary" pending={sync.isPending} onClick={() => sync.mutate()}>
                Sync now
              </Button>
            }
          >
            Pull the public price list once; calls on unknown models are recorded as “unpriced”.
          </Empty>
        ) : (
          <div className={cn("table-wrap transition-opacity", models.isPlaceholderData && "opacity-60")}>
            <table className="table">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Catalog</th>
                  <th className="num">Input</th>
                  <th className="num">Output</th>
                  <th className="num">Cache read</th>
                  <th className="num">Context</th>
                </tr>
              </thead>
              <tbody>
                {models.data?.models.map((m) => (
                  <tr key={`${m.catalog_id}/${m.model_id}`}>
                    <td className="max-w-[22rem]">
                      <div className="truncate font-medium">{m.name}</div>
                      <div className="mono truncate text-xs text-muted">{m.model_id}</div>
                    </td>
                    <td>
                      <div className="flex items-center gap-1.5">
                        <span className="text-ink-2">{m.catalog_id}</span>
                        {m.source === "manual" && <Chip tone="accent">manual</Chip>}
                        {m.reasoning && <Chip>reasoning</Chip>}
                      </div>
                    </td>
                    <td className="num">{perMillion(m.input)}</td>
                    <td className="num">{perMillion(m.output)}</td>
                    <td className="num text-ink-2">{perMillion(m.cache_read)}</td>
                    <td className="num text-ink-2">{m.context_limit ? tokens(m.context_limit) : "—"}</td>
                  </tr>
                ))}
                {models.data && models.data.models.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-10 text-center text-muted">
                      No matches.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
