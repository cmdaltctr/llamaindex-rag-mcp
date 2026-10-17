import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useApi } from "../api/ApiProvider";
import type { NodeControls } from "../api/pipelines";
import { draftCheckQuery } from "../api/queries";
import { fromDocument, toDocument, type Draft, type DraftGraph } from "./graph";

/** How long the graph document must stay unchanged before the canvas checks it. */
export const CHECK_PAUSE_MS = 500;

function useDebounced<T>(value: T, delay: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    if (value === settled) return;
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, settled, delay]);
  return settled;
}

/**
 * Runs the draft check by itself: when a graph opens, and after the graph
 * document stops changing for `CHECK_PAUSE_MS`. Layout edits do not change the
 * document, so they start no check. The query key is the document, so an answer
 * for an older draft is never read. Returns the checked graph with the controls
 * the check reported, or `null` while no answer exists for the settled document.
 * It changes no issue list and no notice: only the user's Validate does that.
 */
export function useDraftCheck(draft: Draft): { graph: DraftGraph; nodes: NodeControls[] } | null {
  const api = useApi();
  const settled = useDebounced(JSON.stringify(toDocument(draft)), CHECK_PAUSE_MS);
  const graph = useMemo(() => fromDocument(JSON.parse(settled), {}).graph, [settled]);
  const query = useQuery({ ...draftCheckQuery(api, settled), enabled: graph.nodes.length > 0 });
  // Memoised: a new object on every render would rebuild every card on the canvas.
  return useMemo(() => (query.data === undefined ? null : { graph, nodes: query.data }), [graph, query.data]);
}
