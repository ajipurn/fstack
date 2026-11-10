import { FileText, Plus } from "@gravity-ui/icons";
import { useState } from "react";
import { useNavigate } from "react-router";
import { ago } from "../../lib/format";
import { useCreatePrompt, usePrompts } from "../../lib/hooks";
import { Button, Chip, Dialog, Empty, Field, Input, PageHeader, Panel, Skeleton, Textarea } from "../../ui";

export function PromptsPage() {
  const prompts = usePrompts();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  return (
    <>
      <PageHeader
        title="Prompts"
        description="Versioned instructions. Drafts autosave, published versions are immutable and fingerprinted, and every call records the exact version it used."
        actions={
          <Button variant="primary" onClick={() => setCreating(true)}>
            <Plus /> New prompt
          </Button>
        }
      />
      <Panel>
        {prompts.isPending ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-8" />
            <Skeleton className="h-8" />
          </div>
        ) : !prompts.data?.length ? (
          <Empty icon={<FileText />} title="No prompts yet" action={<Button onClick={() => setCreating(true)}>Create prompt</Button>}>
            Add one here, or drop a Markdown file in backend/prompts and seed it: uv run tasks.py seed.
          </Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Prompt</th>
                  <th>Active</th>
                  <th className="num">Versions</th>
                  <th>Output</th>
                  <th className="num">Updated</th>
                </tr>
              </thead>
              <tbody>
                {prompts.data.map((p) => (
                  <tr key={p.key} data-clickable="" onClick={() => navigate(`/prompts/${p.key}`)}>
                    <td>
                      <div className="font-medium">{p.name}</div>
                      <div className="mono text-xs text-muted">{p.key}</div>
                    </td>
                    <td>
                      <div className="flex items-center gap-1.5">
                        {p.active_version ? <Chip tone="ok">v{p.active_version}</Chip> : <Chip tone="warn">none</Chip>}
                        {p.has_draft && <Chip tone="accent">draft</Chip>}
                      </div>
                    </td>
                    <td className="num text-ink-2">{p.published_count}</td>
                    <td>{p.structured ? <Chip tone="info">JSON</Chip> : <span className="text-xs text-muted">text</span>}</td>
                    <td className="num text-muted">{ago(p.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <CreatePromptDialog open={creating} onOpenChange={setCreating} />
    </>
  );
}

function CreatePromptDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const create = useCreatePrompt();
  const navigate = useNavigate();
  const [form, setForm] = useState({ key: "", name: "", description: "", system: "", user_template: "{{input}}" });
  const set = (field: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [field]: e.target.value }));
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="New prompt"
      description="Starts as a draft. Publish it to make it callable."
      width="36rem"
      footer={
        <>
          <Button onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            variant="primary"
            pending={create.isPending}
            onClick={() =>
              create.mutate(form, {
                onSuccess: (prompt) => {
                  onOpenChange(false);
                  navigate(`/prompts/${prompt.key}`);
                },
              })
            }
          >
            Create draft
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="Name">
          <Input
            value={form.name}
            onChange={(e) => {
              const name = e.target.value;
              setForm((f) => ({
                ...f,
                name,
                key: f.key && f.key !== slug(f.name) ? f.key : slug(name),
              }));
            }}
            placeholder="Classify ticket"
          />
        </Field>
        <Field label="Key" hint="Used in code and URLs">
          <Input className="mono" value={form.key} onChange={set("key")} placeholder="classify-ticket" />
        </Field>
        <Field label="Description" className="col-span-2">
          <Input value={form.description} onChange={set("description")} />
        </Field>
        <Field label="System" className="col-span-2">
          <Textarea rows={4} className="mono text-xs" value={form.system} onChange={set("system")} />
        </Field>
        <Field label="User template" className="col-span-2" hint="Use {{variable}} placeholders.">
          <Textarea rows={3} className="mono text-xs" value={form.user_template} onChange={set("user_template")} />
        </Field>
      </div>
    </Dialog>
  );
}

function slug(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/^[^a-z]+/, "")
    .slice(0, 60);
}
