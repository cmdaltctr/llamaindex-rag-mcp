import { Button } from "../../components/ui/button";
import { NodeRunStatus } from "../../studio/NodeRunStatus";
import { Panel } from "../Panel";
import { NodeInspector } from "./NodeInspector";
import type { OutcomeRow } from "./outcomeRows";

interface NodeOutcomesProps {
  runId: string;
  rows: OutcomeRow[];
  wallTimeS: number | null;
  selected: string | null;
  onSelect: (key: string) => void;
}

/** Node outcomes and the selected node's inspector. Node times stay separate from the run wall time. */
export function NodeOutcomes({ runId, rows, wallTimeS, selected, onSelect }: NodeOutcomesProps) {
  const chosen = rows.find((row) => row.key === selected) ?? null;
  return (
    <Panel
      title="Node outcomes"
      level={3}
      description={`${wallTimeS !== null ? `Run wall time: ${wallTimeS.toFixed(2)} s. ` : "Run wall time: recorded when the run ends. "}Node times can overlap, so they are not added up.`}
    >
      {rows.length === 0 && <p className="text-meta text-muted-foreground">No node has reported an event yet.</p>}
      <ul className="flex flex-col gap-2">
        {rows.map((row) => (
          <li key={row.key} className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Button
              variant="chip"
              size="sm"
              aria-pressed={row.key === selected}
              aria-label={`Inspect node ${row.nodeId}${row.unitId ? ` for unit ${row.unitId}` : ""}`}
              onClick={() => onSelect(row.key)}
            >
              <code className="font-mono text-code">{row.nodeId}</code>
              {row.unitId && <span className="text-meta text-muted-foreground">{row.unitId}</span>}
            </Button>
            <NodeRunStatus state={row.state} />
          </li>
        ))}
      </ul>
      {chosen && <NodeInspector runId={runId} row={chosen} />}
    </Panel>
  );
}
