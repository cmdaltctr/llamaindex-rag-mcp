import type { MonitorMode } from "./eventClient";
import { maskText } from "./redact";
import { unitCounts, type RunView } from "./runState";
import "./runs.css";

const MODE_TEXT: Record<MonitorMode, string> = {
  connecting: "Connecting to the event stream",
  streaming: "streaming events",
  reconnecting: "reconnecting; events seen so far are kept",
  polling: "polling for events (the event stream is not available)",
  ended: "the run ended",
  closed: "monitoring stopped",
};

interface LiveRunSummaryProps {
  runId: string;
  status: string;
  view: RunView;
  mode: MonitorMode | null;
  /** False for a run that had already finished: its events are a record, not a live run. */
  live: boolean | null;
  error: string | null;
}

/** Run status, event mode, unit counter and committed effects. All figures come from received events. */
export function LiveRunSummary({ runId, status, view, mode, live, error }: LiveRunSummaryProps) {
  const units = unitCounts(view);
  const prefix = live === false ? "Recorded run, not live" : "Live";
  return (
    <section className="live-run" aria-label="Run progress">
      <p className="live-run__status">
        Run <code>{runId}</code>: {status}
      </p>
      <p className="text-meta" aria-live="polite">
        {mode === null ? "Waiting for the run record" : `${prefix}: ${MODE_TEXT[mode]}`}
      </p>
      {units.started > 0 && (
        <p className="text-meta">{`Units: ${units.started} started, ${units.completed} completed, ${units.failed} failed, ${units.cancelled} cancelled`}</p>
      )}
      {view.effects.length > 0 && <p className="text-meta">{`Committed effects so far: ${view.effects.length}`}</p>}
      {view.wallTimeS !== null && <p className="text-meta">{`Run wall time: ${view.wallTimeS.toFixed(2)} s`}</p>}
      {error && <p className="text-meta live-run__error">{`Event monitoring: ${maskText(error)}`}</p>}
    </section>
  );
}
