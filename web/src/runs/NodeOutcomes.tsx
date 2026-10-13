import type { NodeOutcomeRecord } from "../api/runs";
import { NodeRunBadge } from "./NodeRunBadge";
import { NodeRunInspector } from "./NodeRunInspector";
import type { NodeRunState, NodeRunStatus, RunView } from "./runState";

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
        status: (STATUSES.has(node.status) ? node.status : "failed") as NodeRunStatus,
        fallback: node.fallback,
        error: node.error,
        unitId: node.unit_id,
      },
    }));
  }
  return Object.entries(view.nodes).map(([nodeId, state]) => ({ key: nodeId, nodeId, unitId: state.unitId, state, durationS: null, effects: [] }));
}

interface NodeOutcomesProps {
  rows: OutcomeRow[];
  wallTimeS: number | null;
  selected: string | null;
  onSelect: (key: string) => void;
}

/** Node outcomes and the selected node's inspector. Node times stay separate from the run wall time. */
export function NodeOutcomes({ rows, wallTimeS, selected, onSelect }: NodeOutcomesProps) {
  const chosen = rows.find((row) => row.key === selected) ?? null;
  return (
    <section className="run-section" aria-label="Node outcomes">
      <h3 className="text-subsection-title">Node outcomes</h3>
      <p className="text-meta">
        {wallTimeS !== null ? `Run wall time: ${wallTimeS.toFixed(2)} s. ` : "Run wall time: recorded when the run ends. "}
        Node times can overlap, so they are not added up.
      </p>
      {rows.length === 0 && <p className="text-meta">No node has reported an event yet.</p>}
      <ul className="run-outcomes">
        {rows.map((row) => (
          <li key={row.key}>
            <button
              type="button"
              className="button button--ghost button--small"
              aria-pressed={row.key === selected}
              aria-label={`Inspect node ${row.nodeId}${row.unitId ? ` for unit ${row.unitId}` : ""}`}
              onClick={() => onSelect(row.key)}
            >
              <code>{row.nodeId}</code>
              {row.unitId && <span className="text-meta">{row.unitId}</span>}
            </button>
            <NodeRunBadge state={row.state} />
          </li>
        ))}
      </ul>
      {chosen && <NodeRunInspector row={chosen} />}
    </section>
  );
}
