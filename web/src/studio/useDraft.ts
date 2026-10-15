import { useCallback, useEffect, useState } from "react";
import type { Draft } from "./graph";
import { clearDraft, readDraft, writeDraft } from "./storage";

/**
 * The working draft of one pipeline. It starts from the draft the browser
 * holds, or else from `initial` (the saved revision), and it is written to
 * browser storage on every change. Nothing is written before the first change,
 * so a reload never saves the server's own graph over a newer revision.
 * Mount with `key={pipelineId}`: the id is read once.
 */
export function useDraft(pipelineId: string, initial: () => Draft) {
  const [state, setState] = useState(() => ({ draft: readDraft(pipelineId) ?? initial(), changed: false }));

  useEffect(() => {
    if (state.changed) writeDraft(pipelineId, state.draft);
  }, [pipelineId, state]);

  const update = useCallback((change: (draft: Draft) => Draft) => {
    setState((current) => ({ draft: change(current.draft), changed: true }));
  }, []);

  /** A saved revision holds the graph now, so the stored draft goes. The next change stores one again. */
  const markSaved = useCallback(() => {
    clearDraft(pipelineId);
    setState((current) => ({ ...current, changed: false }));
  }, [pipelineId]);

  return { draft: state.draft, update, markSaved };
}
