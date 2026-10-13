import { useCallback, useEffect, useState } from "react";
import { emptyDraft, type Draft } from "./graph";
import { clearDraft, readDraft, writeDraft } from "./storage";

/** Storage key for a draft that has no server pipeline yet. */
export const NEW_DRAFT_KEY = "new";

/** The working draft for one pipeline, saved to browser storage on every change. */
export function useDraft(initialKey: string) {
  // ``persist`` stays false for the empty placeholder shown before a stored
  // pipeline loads, so a reload never saves that placeholder over the
  // pipeline's real draft or revision.
  const [state, setState] = useState(() => {
    const stored = readDraft(initialKey);
    return { key: initialKey, draft: stored ?? emptyDraft(), persist: stored !== null };
  });

  useEffect(() => {
    if (state.persist) writeDraft(state.key, state.draft);
  }, [state]);

  const update = useCallback((change: (draft: Draft) => Draft) => {
    setState((current) => ({ ...current, draft: change(current.draft), persist: true }));
  }, []);

  /** Shows another pipeline's draft. */
  const replace = useCallback((key: string, draft: Draft) => setState({ key, draft, persist: true }), []);

  /** Moves the unsaved draft to the pipeline that the server just created. */
  const adoptNew = useCallback((key: string) => {
    clearDraft(NEW_DRAFT_KEY);
    setState((current) => ({ key, draft: current.draft, persist: true }));
  }, []);

  return { draftKey: state.key, draft: state.draft, update, replace, adoptNew };
}
