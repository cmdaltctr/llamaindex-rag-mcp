import type { NodeOutcomeRecord } from "../../api/runs";
import type { NodeRunState, NodeRunStatus, RunView } from "../../runs/runState";

const STATUSES = new Set<string>(["queued", "running", "succeeded", "failed", "skipped", "bypassed", "cancelled"]);

/** One row per node (and unit): the stored outcome when the run has ended, else the event state. */
export interface OutcomeRow {
  key: string;
  nodeId: string;
  unitId: string | null;
  state: NodeRunState | undefined;
  durationS: number | null;
  effects: string[];
}

export function outcomeRows(nodes: NodeOutcomeRecord[] | undefined, view: RunView): OutcomeRow[] {
  if (nodes && nodes.length > 0) {
    return nodes.map((node, index) => ({
      key: `${node.node_id}-${node.unit_id ?? ""}-${index}`,
      nodeId: node.node_id,
      unitId: node.unit_id,
      durationS: node.duration_s,
      effects: node.effects,
      state: {
        ...(view.nodes[node.node_id] ?? { message: null, summary: null, startedAt: null, endedAt: null }),
        // The stored summary lets a finished run show why a node passed its
        // input through, without replaying the events.
        summary: node.summary ?? view.nodes[node.node_id]?.summary ?? null,
        status: (STATUSES.has(node.status) ? node.status : "failed") as NodeRunStatus,
        fallback: node.fallback,
        error: node.error,
        unitId: node.unit_id,
      },
    }));
  }
  return Object.entries(view.nodes).map(([nodeId, state]) => ({ key: nodeId, nodeId, unitId: state.unitId, state, durationS: null, effects: [] }));
}
