/**
 * Per-browser canvas state: one unsaved draft per pipeline, the open
 * pipeline, and the last submitted run snapshot. Storage can be missing or
 * throw, so every access is guarded and the canvas works without it.
 * The server stays the source of truth for revisions and runs.
 */
import type { GraphDocument } from "../api/pipelines";
import { emptyDraft, type Draft } from "./graph";

const DRAFT_PREFIX = "omrg-canvas-draft:";
const SESSION_KEY = "omrg-canvas-session";
const VERSION = 1;

/** The run that the server admitted, frozen at submission. Later draft edits never change it. */
export interface SubmittedRun {
  runId: string;
  status: string;
  revisionId: string;
  revisionNumber: number;
  document: GraphDocument;
}

export interface CanvasSession {
  pipelineId: string | null;
  run: SubmittedRun | null;
}

function read(key: string): unknown {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? null : (JSON.parse(raw) as unknown);
  } catch {
    return null;
  }
}

function write(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify({ version: VERSION, ...(value as object) }));
  } catch {
    // Storage is a convenience only.
  }
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
  if (!isRecord(value) || value.version !== VERSION || !isRecord(value.graph) || !isRecord(value.layout)) return null;
  const { graph, layout } = value;
  if (!isArray(graph.nodes, isNode) || !isArray(graph.edges, isEdge)) return null;
  if (!Array.isArray(graph.inputs) || !Array.isArray(graph.outputs) || !isRecord(layout.positions)) return null;
  const base = emptyDraft();
  return {
    graph: { ...base.graph, ...(graph as Partial<Draft["graph"]>) },
    layout: { ...base.layout, ...(layout as Partial<Draft["layout"]>) },
  };
}

export function readDraft(pipelineKey: string): Draft | null {
  return asDraft(read(DRAFT_PREFIX + pipelineKey));
}

export function writeDraft(pipelineKey: string, draft: Draft): void {
  write(DRAFT_PREFIX + pipelineKey, draft);
}

export function clearDraft(pipelineKey: string): void {
  try {
    window.localStorage.removeItem(DRAFT_PREFIX + pipelineKey);
  } catch {
    // Ignore: nothing to clear.
  }
}

function asRun(value: unknown): SubmittedRun | null {
  if (!isRecord(value) || typeof value.runId !== "string" || typeof value.revisionId !== "string") return null;
  if (!isRecord(value.document) || !isArray(value.document.nodes, isNode)) return null;
  return value as unknown as SubmittedRun;
}

export function readSession(): CanvasSession {
  const value = read(SESSION_KEY);
  if (!isRecord(value) || value.version !== VERSION) return { pipelineId: null, run: null };
  return {
    pipelineId: typeof value.pipelineId === "string" ? value.pipelineId : null,
    run: asRun(value.run),
  };
}

export function writeSession(session: CanvasSession): void {
  write(SESSION_KEY, session);
}
