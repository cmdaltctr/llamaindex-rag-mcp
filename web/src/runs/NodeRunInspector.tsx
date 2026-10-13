import { scoreText } from "./evidence";
import type { OutcomeRow } from "./NodeOutcomes";
import { maskText } from "./redact";
import { displayStatus, statusLabel } from "./runState";
import { SafeValue } from "./SafeValue";

/** Status, node time, summary, fallback reason and error of one node in a run. */
export function NodeRunInspector({ row }: { row: OutcomeRow }) {
  const { state } = row;
  const summary = state?.summary ?? null;
  const scoreKind = summary && typeof summary.score_kind === "string" ? summary.score_kind : null;
  return (
    <section className="run-section" aria-label={`Node ${row.nodeId}`}>
      <h4 className="text-subsection-title">
        Node <code>{row.nodeId}</code>
        {row.unitId && (
          <>
            {" "}
            for unit <code>{row.unitId}</code>
          </>
        )}
      </h4>
      <p>{`Status: ${statusLabel(displayStatus(state))}`}</p>
      <p className="text-meta">{row.durationS !== null ? `Node time: ${row.durationS.toFixed(2)} s` : "Node time: recorded when the run ends"}</p>
      {state?.fallback && <p>{`Fallback: ${maskText(state.fallback)}`}</p>}
      {state?.error && <p>{`Error: ${maskText(state.error)}`}</p>}
      {state?.message && !state.error && <p className="text-meta">{`Last message: ${maskText(state.message)}`}</p>}
      {scoreKind && <p className="text-meta">{`Output score kind: ${scoreText(null, scoreKind).label}`}</p>}
      {row.effects.length > 0 && <p className="text-meta">{`Committed effects: ${row.effects.map(maskText).join(", ")}`}</p>}
      {summary && (
        <details>
          <summary>Output summary</summary>
          <SafeValue value={summary} />
        </details>
      )}
    </section>
  );
}
