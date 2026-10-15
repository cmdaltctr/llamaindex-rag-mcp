import type { MonitorMode } from "../runs/eventClient";
import { maskText } from "../runs/redact";
import { unitCounts, type RunView } from "../runs/runState";
import { RunStatusBadge } from "./RunStatusBadge";

const MODE_TEXT: Record<MonitorMode, string> = {
  connecting: "Connecting to the event stream",
  streaming: "streaming events",
  reconnecting: "reconnecting; events seen so far are kept",
  polling: "polling for events (the event stream is not available)",
  ended: "the run ended",
  closed: "monitoring stopped",
};

interface RunProgressProps {
  runId: string;
  status: string;
  view: RunView;
  mode: MonitorMode | null;
  /** False for a run that had already finished: its events are a record, not a live run. */
  live: boolean | null;
  error: string | null;
}

/** Run status, event mode, unit counter and committed effects. Every figure comes from a received event. */
export function RunProgress({ runId, status, view, mode, live, error }: RunProgressProps) {
  const units = unitCounts(view);
  const prefix = live === false ? "Recorded run, not live" : "Live";
  return (
    <section aria-label="Run progress" className="flex flex-col gap-1">
      <p className="text-ui">
        Run <code className="font-mono text-code">{runId}</code>: <RunStatusBadge status={status} />
      </p>
      <p className="text-meta text-muted-foreground" aria-live="polite">
        {mode === null ? "Waiting for the run record" : `${prefix}: ${MODE_TEXT[mode]}`}
      </p>
      {units.started > 0 && (
        <p className="text-meta text-muted-foreground">{`Units: ${units.started} started, ${units.completed} completed, ${units.failed} failed, ${units.cancelled} cancelled`}</p>
      )}
      {view.effects.length > 0 && <p className="text-meta text-muted-foreground">{`Committed effects so far: ${view.effects.length}`}</p>}
      {view.wallTimeS !== null && <p className="text-meta text-muted-foreground">{`Run wall time: ${view.wallTimeS.toFixed(2)} s`}</p>}
      {error && <p className="text-meta text-status-error-label">{`Event monitoring: ${maskText(error)}`}</p>}
    </section>
  );
}
