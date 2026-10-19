import { scoreText } from "../../runs/evidence";
import { maskText } from "../../runs/redact";
import { bypassReason, displayStatus, statusLabel } from "../../runs/runState";
import type { OutcomeRow } from "./outcomeRows";
import { OutputCut } from "./OutputViewer";
import { SafeValue } from "./SafeValue";

/** Status, node time, summary, fallback reason and error of one node in a run. */
export function NodeInspector({ runId, row }: { runId: string; row: OutcomeRow }) {
  const { state } = row;
  const summary = state?.summary ?? null;
  const reason = bypassReason(state);
  const scoreKind = summary && typeof summary.score_kind === "string" ? summary.score_kind : null;
  return (
    <section aria-label={`Node ${row.nodeId}`} className="flex flex-col gap-1 rounded-small border border-border p-3 text-ui">
      <h4 className="text-subsection-title font-semibold">
        Node <code className="font-mono text-code">{row.nodeId}</code>
        {row.unitId && (
          <>
            {" "}
            for unit <code className="font-mono text-code">{row.unitId}</code>
          </>
        )}
      </h4>
      <p>{`Status: ${statusLabel(displayStatus(state))}`}</p>
      <p className="text-meta text-muted-foreground">{row.durationS !== null ? `Node time: ${row.durationS.toFixed(2)} s` : "Node time: recorded when the run ends"}</p>
      {reason && <p>{`Bypass reason: ${maskText(reason)}`}</p>}
      {state?.fallback && <p>{`Fallback: ${maskText(state.fallback)}`}</p>}
      {state?.error && <p>{`Error: ${maskText(state.error)}`}</p>}
      {state?.message && !state.error && <p className="text-meta text-muted-foreground">{`Last message: ${maskText(state.message)}`}</p>}
      {scoreKind && <p className="text-meta text-muted-foreground">{`Output score kind: ${scoreText(null, scoreKind).label}`}</p>}
      {row.effects.length > 0 && <p className="text-meta text-muted-foreground">{`Committed effects: ${row.effects.map(maskText).join(", ")}`}</p>}
      {summary && (
        <details className="pt-1">
          <summary className="cursor-pointer font-medium">Output summary</summary>
          <div className="pt-2">
            <SafeValue value={summary} />
          </div>
        </details>
      )}
      {summary && <OutputCut runId={runId} name={`node-${row.nodeId}-summary`} value={summary} />}
    </section>
  );
}
