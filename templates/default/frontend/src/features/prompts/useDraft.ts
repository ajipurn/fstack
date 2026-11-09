import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "../../lib/api";
import { useSaveDraft } from "../../lib/hooks";
import { keys, queryClient } from "../../lib/query";
import type { PromptDetail, PromptVersion } from "../../lib/types";

export type DraftFields = { system: string; user_template: string; note: string };
export type SaveState = "saved" | "dirty" | "saving" | "error";

/** Debounced autosave with optimistic locking (revision) and unload guard. */
export function useDraft(promptKey: string, draft: PromptVersion) {
  const save = useSaveDraft(promptKey);
  const [fields, setFields] = useState<DraftFields>({ system: draft.system, user_template: draft.user_template, note: draft.note });
  const [state, setState] = useState<SaveState>("saved");
  const [error, setError] = useState("");
  const revision = useRef(draft.revision);
  const latest = useRef(fields);
  const saved = useRef(JSON.stringify(fields));
  const inflight = useRef<Promise<void> | null>(null);

  const flush = useCallback(async () => {
    while (JSON.stringify(latest.current) !== saved.current) {
      if (inflight.current) {
        await inflight.current;
        continue;
      }
      const snapshot = latest.current;
      setState("saving");
      inflight.current = save
        .mutateAsync({ ...snapshot, revision: revision.current })
        .then((version) => {
          revision.current = version.revision;
          saved.current = JSON.stringify(snapshot);
          queryClient.setQueryData<PromptDetail>(keys.prompt(promptKey), (p) =>
            p ? { ...p, versions: p.versions.map((v) => (v.id === version.id ? { ...v, ...version } : v)) } : p,
          );
        })
        .finally(() => {
          inflight.current = null;
        });
      try {
        await inflight.current;
      } catch (e) {
        setState("error");
        setError(errorMessage(e));
        throw e;
      }
    }
    setState("saved");
    setError("");
  }, [promptKey, save]);

  const change = (patch: Partial<DraftFields>) => {
    latest.current = { ...latest.current, ...patch };
    setFields(latest.current);
    setState("dirty");
  };

  useEffect(() => {
    if (state !== "dirty") return;
    const timer = setTimeout(() => void flush().catch(() => {}), 800);
    return () => clearTimeout(timer);
  }, [fields, state, flush]);

  useEffect(() => {
    const guard = (e: BeforeUnloadEvent) => {
      if (JSON.stringify(latest.current) !== saved.current) e.preventDefault();
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, []);

  return { fields, change, state, error, flush, revision };
}
