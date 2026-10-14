import { scoreText } from "./evidence";
import type { OutcomeRow } from "./NodeOutcomes";
import { maskText } from "./redact";
import { bypassReason, displayStatus, statusLabel } from "./runState";
import { SafeValue } from "./SafeValue";

/** Status, node time, summary, fallback reason and error of one node in a run. */
export function NodeRunInspector({ row }: { row: OutcomeRow }) {
  const { state } = row;
  const summary = state?.summary ?? null;
  const reason = bypassReason(state);
  const scoreKind = summary && typeof summary.score_kind === "string" ? summary.score_kind : null;
  return (
    <section className="run-section" aria-label={`Node ${row.nodeId}`}>
      <h4>
        Node <code>{row.nodeId}</code>
        {row.unitId && (
          <>
            {" "}
            for unit <code>{row.unitId}</code>
          </>
        )}
      </h4>
      <p>{`Status: ${statusLabel(displayStatus(state))}`}</p>
      <p className="type-meta">{row.durationS !== null ? `Node time: ${row.durationS.toFixed(2)} s` : "Node time: recorded when the run ends"}</p>
      {reason && <p>{`Bypass reason: ${maskText(reason)}`}</p>}
      {state?.fallback && <p>{`Fallback: ${maskText(state.fallback)}`}</p>}
      {state?.error && <p>{`Error: ${maskText(state.error)}`}</p>}
      {state?.message && !state.error && <p className="type-meta">{`Last message: ${maskText(state.message)}`}</p>}
      {scoreKind && <p className="type-meta">{`Output score kind: ${scoreText(null, scoreKind).label}`}</p>}
      {row.effects.length > 0 && <p className="type-meta">{`Committed effects: ${row.effects.map(maskText).join(", ")}`}</p>}
      {summary && (
        <details>
          <summary>Output summary</summary>
          <SafeValue value={summary} />
        </details>
      )}
    </section>
  );
}
