/** The starting draft of an opened pipeline. The saved revision, not the draft, decides execution. */
import type { GraphLayout, PipelineRecord, RevisionRecord } from "../api/pipelines";
import { fromDocument, type Draft } from "./graph";

const gridSlot = (index: number) => ({ x: 40 + 260 * (index % 4), y: 40 + 180 * Math.floor(index / 4) });

/**
 * The draft of an opened pipeline when the browser holds none: its saved
 * revision and layout. Nodes without a saved position (a revision saved before
 * the layout) go to free grid slots, so none stack at the origin.
 */
export function initialDraft(pipeline: PipelineRecord, revision: RevisionRecord | null): Draft {
  const layout: GraphLayout = { ...pipeline.layout };
  const draft = fromDocument(revision?.document ?? null, layout);
  const missing = draft.graph.nodes.map((node) => node.id).filter((id) => draft.layout.positions[id] === undefined);
  if (missing.length === 0) return draft;
  const taken = new Set(Object.values(draft.layout.positions).map((at) => `${at.x},${at.y}`));
  const placed: Record<string, { x: number; y: number }> = {};
  let index = 0;
  for (const id of missing) {
    while (taken.has(`${gridSlot(index).x},${gridSlot(index).y}`)) index += 1;
    placed[id] = gridSlot(index);
    index += 1;
  }
  return { ...draft, layout: { ...draft.layout, positions: { ...draft.layout.positions, ...placed } } };
}
