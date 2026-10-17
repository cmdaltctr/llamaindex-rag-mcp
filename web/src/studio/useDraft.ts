import { useCallback, useEffect, useState } from "react";
import type { Draft } from "./graph";
import { clearDraft, readDraft, writeDraft } from "./storage";

/**
 * The working draft of one pipeline. It starts from the draft the browser
 * holds, or else from `initial` (the saved revision), and it is written to
 * browser storage on every change. Nothing is written before the first change,
 * so a reload never saves the server's own graph over a newer revision.
 * With `persist: false` (a read-only graph) the draft starts from `initial`
 * and never touches browser storage; selection and viewport stay in memory.
 * Mount with `key={pipelineId}`: the id and the option are read once.
 */
export function useDraft(pipelineId: string, initial: () => Draft, { persist = true }: { persist?: boolean } = {}) {
  const [state, setState] = useState(() => ({ draft: (persist ? readDraft(pipelineId) : null) ?? initial(), changed: false }));

  useEffect(() => {
    if (persist && state.changed) writeDraft(pipelineId, state.draft);
  }, [persist, pipelineId, state]);

  const update = useCallback((change: (draft: Draft) => Draft) => {
    setState((current) => ({ draft: change(current.draft), changed: true }));
  }, []);

  /** A saved revision holds the graph now, so the stored draft goes. The next change stores one again. */
  const markSaved = useCallback(() => {
    if (persist) clearDraft(pipelineId);
    setState((current) => ({ ...current, changed: false }));
  }, [persist, pipelineId]);

  return { draft: state.draft, update, markSaved };
}
