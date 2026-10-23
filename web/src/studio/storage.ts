/**
 * Per-browser canvas state: one unsaved draft per pipeline, kept under
 * `omrs-canvas-draft:<pipeline-id>` and cleared when a revision is saved.
 * Browser storage can be blocked, so each draft is also held in memory for the
 * rest of the session: a graph seeded from a gallery card still opens, and
 * edits survive moving between areas. The server stays the source of truth
 * for revisions and runs, and the open pipeline comes from the route.
 */
import { emptyDraft, type Draft } from "./graph";
import { readStored, removeStored, writeStored } from "../lib/storage";

export const DRAFT_PREFIX = "omrs-canvas-draft:";

const sessionDrafts = new Map<string, Draft>();

/** Forgets every in-memory draft. Tests call it between cases; the app never needs to. */
export function resetSessionDrafts(): void {
  sessionDrafts.clear();
}

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;
const isArray = (value: unknown, check: (item: unknown) => boolean) => Array.isArray(value) && value.every(check);

function isNode(value: unknown): boolean {
  return isRecord(value) && typeof value.id === "string" && typeof value.operation === "string";
}

function isEdge(value: unknown): boolean {
  const ref = (r: unknown) => isRecord(r) && typeof r.node === "string" && typeof r.port === "string";
  return isRecord(value) && ref(value.source) && ref(value.target);
}

function asDraft(value: unknown): Draft | null {
  if (!isRecord(value) || !isRecord(value.graph) || !isRecord(value.layout)) return null;
  const { graph, layout } = value;
  if (!isArray(graph.nodes, isNode) || !isArray(graph.edges, isEdge)) return null;
  if (!Array.isArray(graph.inputs) || !Array.isArray(graph.outputs) || !isRecord(layout.positions)) return null;
  const base = emptyDraft();
  const kept = Object.fromEntries(Object.entries(layout).filter(([key]) => key !== "title")); // earlier versions stored a title
  return {
    graph: { ...base.graph, ...(graph as Partial<Draft["graph"]>) },
    layout: { ...base.layout, ...(kept as Partial<Draft["layout"]>) },
  };
}

function isDraft(value: unknown): value is Draft {
  return asDraft(value) !== null;
}

export function readDraft(pipelineKey: string): Draft | null {
  const stored = readStored(DRAFT_PREFIX + pipelineKey, isDraft);
  return (stored === null ? null : asDraft(stored)) ?? sessionDrafts.get(pipelineKey) ?? null;
}

export function writeDraft(pipelineKey: string, draft: Draft): void {
  sessionDrafts.set(pipelineKey, draft);
  writeStored(DRAFT_PREFIX + pipelineKey, draft);
}

export function clearDraft(pipelineKey: string): void {
  sessionDrafts.delete(pipelineKey);
  removeStored(DRAFT_PREFIX + pipelineKey);
}
