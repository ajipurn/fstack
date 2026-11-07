import { ArrowLeft, CircleCheck, CodeCompare, PencilToSquare, Play, TrashBin } from "@gravity-ui/icons";
import { diffLines } from "diff";
import { Fragment, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ago, dateTime } from "../../lib/format";
import { useActivate, useDeletePrompt, useDiscardDraft, usePrompt, usePublish, useStartDraft } from "../../lib/hooks";
import type { PromptDetail, PromptVersion } from "../../lib/types";
import { Button, buttonClass, Chip, cn, ConfirmDialog, Dialog, Field, Input, PageHeader, Panel, Segmented, Select, Skeleton, Spinner, Switch, Textarea } from "../../ui";
import { useDraft, type SaveState } from "./useDraft";

export function PromptDetailPage() {
  const { key = "" } = useParams();
  const prompt = usePrompt(key);
  const [selected, setSelected] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const remove = useDeletePrompt(key);
  const navigate = useNavigate();
  if (prompt.isPending) return <Skeleton className="h-96" />;
  if (!prompt.data) return <p className="text-sm text-muted">Prompt not found.</p>;
  const p = prompt.data;
  const draft = p.versions.find((v) => v.status === "draft");
  const current = p.versions.find((v) => v.id === selected) ?? draft ?? p.versions.find((v) => v.id === p.active_version_id) ?? p.versions[0];

  return (
    <>
      <Link to="/prompts" className="mb-3 inline-flex items-center gap-1.5 text-xs text-muted transition-colors hover:text-ink [&_svg]:size-3.5">
        <ArrowLeft /> Prompts
      </Link>
      <PageHeader
        title={p.name}
        description={p.description || undefined}
        eyebrow={<span className="mono">{p.key}</span>}
        actions={
          <div className="flex items-center gap-2">
            {p.structured && <Chip tone="info">JSON output</Chip>}
            <Button size="sm" variant="ghost" onClick={() => setDeleting(true)}>
              <TrashBin /> Delete
            </Button>
            <Link to={`/run?prompt=${encodeURIComponent(p.key)}`} className={buttonClass({ size: "sm" })}>
              <Play /> Run
            </Link>
          </div>
        }
      />
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete ${p.name}?`}
        description={`Removes “${p.key}” and all ${p.versions.length} of its versions. Usage history keeps the prompt key. If backend/prompts/${p.key}.md still exists, make seed brings it back.`}
        confirmLabel="Delete prompt"
        destructive
        pending={remove.isPending}
        onConfirm={() => remove.mutate(undefined, { onSuccess: () => navigate("/prompts") })}
      />
      <div className="grid gap-3 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <VersionList prompt={p} current={current} onSelect={setSelected} />
        {current ? (
          current.status === "draft" ? (
            <DraftEditor key={current.id} prompt={p} draft={current} />
          ) : (
            <VersionView key={current.id} prompt={p} version={current} hasDraft={!!draft} onDraft={() => setSelected(null)} />
          )
        ) : null}
      </div>
    </>
  );
}

function VersionList({ prompt, current, onSelect }: { prompt: PromptDetail; current?: PromptVersion; onSelect: (id: string) => void }) {
  return (
    <Panel title={`Versions · ${prompt.versions.length}`} className="self-start">
      <ol className="relative p-1.5">
        {prompt.versions.map((v) => {
          const active = v.id === prompt.active_version_id;
          const isCurrent = v.id === current?.id;
          return (
            <li key={v.id}>
              <button
                type="button"
                onClick={() => onSelect(v.id)}
                className={cn(
                  "flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors",
                  isCurrent ? "bg-surface-3" : "hover:bg-surface-2",
                )}
              >
                <span
                  className={cn(
                    "mt-[5px] size-2 shrink-0 rounded-full",
                    v.status === "draft" ? "bg-transparent shadow-[inset_0_0_0_1.5px_var(--accent)]" : active ? "bg-ok" : "bg-line-3",
                  )}
                />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5 text-sm font-medium">
                    v{v.version}
                    {v.status === "draft" && <Chip tone="accent">draft</Chip>}
                    {active && <Chip tone="ok">active</Chip>}
                  </span>
                  <span className="block truncate text-xs text-muted">{v.note || (v.source === "file" ? "from file" : "—")}</span>
                  <span className="block text-[11px] text-faint">
                    {ago(v.published_at ?? v.created_at)}
                    {v.call_count > 0 && ` · ${v.call_count} calls`}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}

/** Renders a template with {{variables}} highlighted. */
function Template({ text }: { text: string }) {
  const parts = text.split(/(\{\{\s*[a-z][a-z0-9_]*\s*\}\})/g);
  return (
    <pre className="code min-h-[3rem]">
      {text ? parts.map((part, i) => (i % 2 ? <span key={i} className="var-token">{part}</span> : <Fragment key={i}>{part}</Fragment>)) : <span className="text-faint">empty</span>}
    </pre>
  );
}

function Section({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section>
      <div className="mb-1.5 flex items-center justify-between">
        <h3 className="text-xs font-medium text-muted">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

function VersionView({ prompt, version, hasDraft, onDraft }: { prompt: PromptDetail; version: PromptVersion; hasDraft: boolean; onDraft: () => void }) {
  const activate = useActivate(prompt.key);
  const startDraft = useStartDraft(prompt.key);
  const [mode, setMode] = useState<"view" | "diff">("view");
  const others = prompt.versions.filter((v) => v.id !== version.id);
  const [against, setAgainst] = useState(others.find((v) => v.version < version.version)?.id ?? others[0]?.id ?? "");
  const base = prompt.versions.find((v) => v.id === against);
  const isActive = version.id === prompt.active_version_id;

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          v{version.version}
          <span className="mono text-[11px] text-faint">{version.digest.slice(0, 12)}</span>
        </span>
      }
      actions={
        <div className="flex items-center gap-1.5">
          {others.length > 0 && (
            <Segmented
              aria-label="View"
              value={mode}
              onChange={setMode}
              options={[
                { value: "view", label: "Content" },
                { value: "diff", label: "Changes" },
              ]}
            />
          )}
          {!hasDraft && (
            <Button size="sm" pending={startDraft.isPending} onClick={() => startDraft.mutate(version.id, { onSuccess: onDraft })}>
              <PencilToSquare /> Edit as new draft
            </Button>
          )}
          {!isActive && (
            <Button size="sm" variant="primary" pending={activate.isPending} onClick={() => activate.mutate(version.id)}>
              <CircleCheck /> Activate
            </Button>
          )}
        </div>
      }
      footer={
        <>
          <span>
            Published {dateTime(version.published_at)}
          </span>
          <span>{version.call_count} calls</span>
        </>
      }
      bodyClassName="p-4 space-y-4"
    >
      {mode === "diff" && base ? (
        <>
          <div className="flex items-center gap-2 text-xs text-muted">
            <CodeCompare className="size-3.5" /> Compared with
            <div className="w-44">
              <Select
                size="sm"
                value={against}
                onChange={setAgainst}
                options={others.map((v) => ({ value: v.id, label: `v${v.version} · ${v.status}` }))}
              />
            </div>
          </div>
          <Section title="System">
            <Diff before={base.system} after={version.system} />
          </Section>
          <Section title="User template">
            <Diff before={base.user_template} after={version.user_template} />
          </Section>
        </>
      ) : (
        <>
          <Section title="System">
            <Template text={version.system} />
          </Section>
          <Section
            title="User template"
            aside={
              <div className="flex gap-1">
                {version.variables.map((v) => (
                  <Chip key={v} tone="accent">
                    {v}
                  </Chip>
                ))}
              </div>
            }
          >
            <Template text={version.user_template} />
          </Section>
        </>
      )}
    </Panel>
  );
}

function Diff({ before, after }: { before: string; after: string }) {
  const parts = useMemo(() => diffLines(before, after), [before, after]);
  const changed = parts.some((p) => p.added || p.removed);
  return (
    <pre className="code diff !px-0">
      {!changed && <span className="text-faint">No changes</span>}
      {changed &&
        parts.map((part, i) =>
          part.value
            .replace(/\n$/, "")
            .split("\n")
            .map((line, j) => (
              <span key={`${i}-${j}`} className={part.added ? "diff-add" : part.removed ? "diff-del" : ""}>
                {part.added ? "+ " : part.removed ? "− " : "  "}
                {line}
              </span>
            )),
        )}
    </pre>
  );
}

const SAVE_LABEL: Record<SaveState, ReactNode> = {
  saved: <span className="text-muted">Saved</span>,
  dirty: <span className="text-muted">Unsaved changes</span>,
  saving: (
    <span className="inline-flex items-center gap-1.5 text-muted">
      <Spinner className="size-3" /> Saving
    </span>
  ),
  error: <span className="text-danger-ink">Not saved</span>,
};

function DraftEditor({ prompt, draft }: { prompt: PromptDetail; draft: PromptVersion }) {
  const { fields, change, state, error, flush, revision } = useDraft(prompt.key, draft);
  const publish = usePublish(prompt.key);
  const discard = useDiscardDraft(prompt.key);
  const [publishing, setPublishing] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [activateNow, setActivateNow] = useState(true);
  const vars = useMemo(() => {
    const found = new Set<string>();
    for (const m of `${fields.system}\n${fields.user_template}`.matchAll(/\{\{\s*([a-z][a-z0-9_]*)\s*\}\}/g)) found.add(m[1]);
    return [...found];
  }, [fields.system, fields.user_template]);

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          Draft v{draft.version} <span className="text-[11px] font-normal">{SAVE_LABEL[state]}</span>
        </span>
      }
      actions={
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="danger-soft" onClick={() => setDiscarding(true)}>
            <TrashBin /> Discard
          </Button>
          <Button
            size="sm"
            variant="primary"
            disabled={!fields.user_template.trim()}
            onClick={async () => {
              await flush().catch(() => {});
              setPublishing(true);
            }}
          >
            Publish…
          </Button>
        </div>
      }
      footer={
        <>
          <span>{error || "Changes save automatically."}</span>
          <span>{`${fields.system.length + fields.user_template.length} chars`}</span>
        </>
      }
      bodyClassName="p-4 space-y-4"
    >
      <Field label="System">
        <Textarea
          rows={10}
          spellCheck={false}
          className="mono text-xs leading-relaxed"
          value={fields.system}
          onChange={(e) => change({ system: e.target.value })}
        />
      </Field>
      <Field
        label={
          <span className="flex items-center justify-between">
            User template
            <span className="flex gap-1">
              {vars.map((v) => (
                <Chip key={v} tone="accent">
                  {v}
                </Chip>
              ))}
            </span>
          </span>
        }
        hint="Variables are the {{placeholders}} across both fields; callers must pass every one."
      >
        <Textarea
          rows={6}
          spellCheck={false}
          className="mono text-xs leading-relaxed"
          value={fields.user_template}
          onChange={(e) => change({ user_template: e.target.value })}
        />
      </Field>

      <Dialog
        open={publishing}
        onOpenChange={setPublishing}
        title={`Publish v${draft.version}`}
        description="Published versions are immutable. Every call records the version and its SHA-256."
        width="28rem"
        footer={
          <>
            <Button onClick={() => setPublishing(false)}>Cancel</Button>
            <Button
              variant="primary"
              pending={publish.isPending}
              onClick={async () => {
                await flush().catch(() => {}); // the note may still be autosaving
                publish.mutate(
                  { revision: revision.current, note: fields.note, activate: activateNow },
                  { onSuccess: () => setPublishing(false) },
                );
              }}
            >
              Publish{activateNow ? " & activate" : ""}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Change note" hint="Shown in the version history.">
            <Input autoFocus value={fields.note} placeholder="Tighter instructions for dates" onChange={(e) => change({ note: e.target.value })} />
          </Field>
          <label className="flex items-center justify-between gap-4 rounded-lg bg-surface-2 px-3 py-2.5 text-sm shadow-[inset_0_0_0_1px_var(--line)]">
            <span>
              <span className="block font-medium">Activate immediately</span>
              <span className="block text-xs text-muted">Runs of “{prompt.key}” use this version from now on.</span>
            </span>
            <Switch checked={activateNow} onChange={setActivateNow} aria-label="Activate immediately" />
          </label>
        </div>
      </Dialog>
      <ConfirmDialog
        open={discarding}
        onOpenChange={setDiscarding}
        title="Discard this draft?"
        description="The draft is deleted. Published versions are untouched."
        confirmLabel="Discard draft"
        destructive
        pending={discard.isPending}
        onConfirm={() => discard.mutate(undefined, { onSuccess: () => setDiscarding(false) })}
      />
    </Panel>
  );
}
