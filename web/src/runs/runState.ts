/**
 * Folds run events into the state the canvas and Runs view display.
 *
 * Only events set state. A node with no event has no state and is shown as
 * "Not started". Nothing here computes percentages, rates or estimates.
 */
import type { RunEventRecord } from "../api/runs";

export type NodeRunStatus = "queued" | "running" | "succeeded" | "failed" | "skipped" | "bypassed" | "cancelled";
export type NodeDisplayStatus = NodeRunStatus | "fallback";

export interface NodeRunState {
  status: NodeRunStatus;
  fallback: string | null;
  error: string | null;
  message: string | null;
  summary: Record<string, unknown> | null;
  unitId: string | null;
  startedAt: string | null;
  endedAt: string | null;
}

export interface UnitCounts {
  started: number;
  completed: number;
  failed: number;
  cancelled: number;
}

export interface RunView {
  lastSequence: number;
  runStatus: string | null;
  nodes: Readonly<Record<string, NodeRunState>>;
  units: Readonly<Record<string, "running" | "completed" | "failed" | "cancelled">>;
  effects: readonly string[];
  wallTimeS: number | null;
  failure: Record<string, unknown> | null;
}

export const EMPTY_RUN_VIEW: RunView = {
  lastSequence: 0,
  runStatus: null,
  nodes: {},
  units: {},
  effects: [],
  wallTimeS: null,
  failure: null,
};

const NODE_STATUS: Record<string, NodeRunStatus> = {
  node_queued: "queued",
  node_started: "running",
  node_progress: "running",
  node_completed: "succeeded",
  node_failed: "failed",
  node_skipped: "skipped",
  node_bypassed: "bypassed",
  node_cancelled: "cancelled",
};

const UNIT_STATUS: Record<string, RunView["units"][string]> = {
  unit_started: "running",
  unit_completed: "completed",
  unit_failed: "failed",
  unit_cancelled: "cancelled",
};

const ENDED = new Set<NodeRunStatus>(["succeeded", "failed", "skipped", "bypassed", "cancelled"]);

function text(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function nodeUpdate(previous: NodeRunState | undefined, event: RunEventRecord): NodeRunState {
  const message = text(event.summary.message);
  const base: NodeRunState = previous ?? {
    status: "queued",
    fallback: null,
    error: null,
    message: null,
    summary: null,
    unitId: null,
    startedAt: null,
    endedAt: null,
  };
  if (event.kind === "node_fallback") return { ...base, fallback: message ?? "A fallback applied; the server gave no reason." };
  const status = NODE_STATUS[event.kind]!;
  const next: NodeRunState = { ...base, status, unitId: event.unit_id ?? base.unitId, message: message ?? base.message };
  if (event.kind === "node_started") Object.assign(next, { startedAt: event.created_at, endedAt: null, error: null, fallback: null });
  if (event.kind === "node_completed") next.summary = record(event.summary.data);
  if (event.kind === "node_failed") next.error = message ?? "The node failed; the server gave no message.";
  if (ENDED.has(status)) next.endedAt = event.created_at;
  return next;
}

/** Applies one event. Returns the same object for a sequence already applied. */
export function applyEvent(view: RunView, event: RunEventRecord): RunView {
  if (event.sequence <= view.lastSequence) return view;
  const next: RunView = { ...view, lastSequence: event.sequence };
  if (event.node_id && (event.kind in NODE_STATUS || event.kind === "node_fallback")) {
    next.nodes = { ...view.nodes, [event.node_id]: nodeUpdate(view.nodes[event.node_id], event) };
  } else if (event.unit_id && event.kind in UNIT_STATUS) {
    next.units = { ...view.units, [event.unit_id]: UNIT_STATUS[event.kind]! };
  } else if (event.kind === "effect_committed") {
    const effect = text(record(event.summary.data)?.effect) ?? text(event.summary.message) ?? event.unit_id ?? event.node_id;
    if (effect && !view.effects.includes(effect)) next.effects = [...view.effects, effect];
  } else if (event.kind === "run.status") {
    next.runStatus = text(event.summary.status) ?? view.runStatus;
    const wall = event.summary.wall_time_s;
    if (typeof wall === "number") next.wallTimeS = wall;
    if (next.runStatus !== "running" && next.runStatus !== "cancelling" && next.runStatus !== "succeeded") next.failure = event.summary;
  }
  return next;
}

export function foldEvents(events: readonly RunEventRecord[], start: RunView = EMPTY_RUN_VIEW): RunView {
  return events.reduce(applyEvent, start);
}

export function unitCounts(view: RunView): UnitCounts {
  const states = Object.values(view.units);
  return {
    started: states.length,
    completed: states.filter((s) => s === "completed").length,
    failed: states.filter((s) => s === "failed").length,
    cancelled: states.filter((s) => s === "cancelled").length,
  };
}

export function displayStatus(node: NodeRunState | undefined): NodeDisplayStatus | null {
  if (!node) return null;
  return node.status === "succeeded" && node.fallback ? "fallback" : node.status;
}

const LABELS: Record<NodeDisplayStatus, string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Completed",
  failed: "Failed",
  skipped: "Skipped",
  bypassed: "Bypassed",
  cancelled: "Cancelled",
  fallback: "Fallback",
};

export function statusLabel(status: NodeDisplayStatus | null): string {
  return status ? LABELS[status] : "Not started";
}

/** An edge is active only while its target node runs. Reduced motion keeps a static highlight. */
export function edgeRunStyle(target: NodeRunStatus | undefined, reducedMotion: boolean): { animated: boolean; className: string | undefined } {
  if (target !== "running") return { animated: false, className: undefined };
  return { animated: !reducedMotion, className: "flow-edge--active" };
}
