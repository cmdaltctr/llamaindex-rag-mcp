/**
 * Starting drafts for a pipeline. A template is an editable starting point:
 * the saved revision, not the template, decides execution. A profile preset is
 * the search template with the retrieval defaults of one operational profile.
 */
import type { GraphLayout, PipelineRecord, PipelineTemplate, RevisionRecord } from "../api/pipelines";
import { emptyDraft, fromDocument, setCollection, setParam, setProfile, setTitle, type Draft } from "./graph";

export type PresetProfile = "documents" | "codebase";

/** The profile presets of the gallery, in display order. */
export const PRESET_PROFILES: readonly PresetProfile[] = ["documents", "codebase"];

/** Retrieval defaults per profile (design D3): the reranker is on for documents and off for codebase. */
const PROFILE_RERANK: Record<PresetProfile, boolean> = { documents: true, codebase: false };

const PRESET_TITLES: Record<PresetProfile, string> = { documents: "Documents search", codebase: "Codebase search" };

export const presetTitle = (profile: PresetProfile): string => PRESET_TITLES[profile];

const gridSlot = (index: number) => ({ x: 40 + 260 * (index % 4), y: 40 + 180 * Math.floor(index / 4) });

/** Positions on the grid that `addNode` uses, four columns wide. */
export function gridPositions(nodeIds: readonly string[]): Record<string, { x: number; y: number }> {
  return Object.fromEntries(nodeIds.map((id, index) => [id, gridSlot(index)]));
}

/** A new draft from a template document, laid out on the grid. */
export function templateDraft(template: PipelineTemplate): Draft {
  return fromDocument(template.document, { title: template.title, positions: gridPositions(template.document.nodes.map((node) => node.id)) });
}

export function blankDraft(title: string): Draft {
  return emptyDraft(title);
}

/**
 * The search template with one profile's retrieval defaults and the target
 * collection. The rerank control is the node parameter `enabled`, which
 * writes the `retrieval.rerank_enabled` lever. The node stays in the graph,
 * so a run still records why inference was skipped.
 */
export function presetDraft(search: PipelineTemplate, profile: PresetProfile, collection: string | null): Draft {
  let draft = setTitle(templateDraft(search), PRESET_TITLES[profile]);
  draft = setCollection(setProfile(draft, profile), collection);
  for (const node of draft.graph.nodes) {
    if (node.operation === "select.rerank") draft = setParam(draft, node.id, "enabled", PROFILE_RERANK[profile]);
  }
  return draft;
}

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
