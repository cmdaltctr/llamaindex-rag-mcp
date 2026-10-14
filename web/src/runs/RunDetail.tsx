import { useEffect, useState } from "react";
import type { FetchLike } from "../api/client";
import {
  ACTIVE_RUN_STATUSES,
  cancelRunRecord,
  getRunRecord,
  getRunResult,
  RETRYABLE_RUN_STATUSES,
  retryRun,
  type RunDetailRecord,
  type RunResultRecord,
} from "../api/runs";
import { EvidenceInspector } from "./EvidenceInspector";
import { LiveRunSummary } from "./LiveRunSummary";
import { NodeOutcomes, outcomeRows } from "./NodeOutcomes";
import { maskText } from "./redact";
import { ReplayPanel } from "./ReplayPanel";
import { RunSnapshot } from "./RunSnapshot";
import { useRunMonitor } from "./useRunMonitor";

interface RunDetailProps {
  runId: string;
  fetchImpl?: FetchLike;
  /** The run list should refresh: a status changed or a new run exists. */
  onChanged: () => void;
  onOpenRun: (runId: string) => void;
}

function errorText(error: unknown): string {
  return maskText(error instanceof Error ? error.message : String(error));
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function originText(run: RunDetailRecord): string {
  if (run.origin === "retry") return `Retry of run ${run.source_run_id ?? "unknown"}`;
  if (run.origin === "repeat") return "Explicit repeat of a saved revision";
  return "Submitted from a saved revision";
}

/** One run: snapshot, live progress or replay, node outcomes, completed effects and evidence. */
export function RunDetail({ runId, fetchImpl, onChanged, onOpenRun }: RunDetailProps) {
  const [run, setRun] = useState<RunDetailRecord | null>(null);
  const [result, setResult] = useState<RunResultRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const active = run !== null && ACTIVE_RUN_STATUSES.has(run.status);
  const monitor = useRunMonitor(active ? runId : null, { fetchImpl });
  // Set when live monitoring saw the run end: read the authoritative record and result again.
  const ended = monitor.refreshedStatus;

  useEffect(() => {
    let live = true;
    getRunRecord(runId, { fetchImpl })
      .then(async (record) => {
        const stored = ACTIVE_RUN_STATUSES.has(record.status) ? null : await getRunResult(runId, { fetchImpl });
        if (!live) return;
        setRun(record);
        setResult(stored);
        if (ended !== null) onChanged();
      })
      .catch((failure: unknown) => live && setError(errorText(failure)));
    return () => {
      live = false;
    };
  }, [runId, fetchImpl, ended, onChanged]);

  async function act(work: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setBusy(false);
    }
  }

  if (!run) {
    return <p className="type-meta">{error ? `Could not open run ${runId}: ${error}` : `Loading run ${runId}.`}</p>;
  }

  const failure = run.failure;
  const effects = [...new Set([...strings(result?.completed_effects), ...strings(failure?.completed_effects), ...monitor.view.effects])];
  const wallTimeS = typeof result?.wall_time_s === "number" ? result.wall_time_s : monitor.view.wallTimeS;
  const rows = outcomeRows(result?.nodes, monitor.view);
  const collections = Object.keys(run.settings);
  const status = monitor.view.runStatus ?? run.status;

  return (
    <section className="run-detail" aria-label={`Run ${run.run_id}`}>
      <h2 className="type-section-title">
        Run <code>{run.run_id}</code>: {status}
      </h2>
      <p className="type-meta">{originText(run)}</p>
      <div className="run-actions">
        {active && (
          <button type="button" className="button" disabled={busy} onClick={() => act(async () => setRun(await cancelRunRecord(runId, { fetchImpl })))}>
            Cancel run
          </button>
        )}
        {RETRYABLE_RUN_STATUSES.has(run.status) && (
          <button
            type="button"
            className="button button--tinted"
            disabled={busy}
            onClick={() =>
              act(async () => {
                const retried = await retryRun(runId, { fetchImpl });
                onChanged();
                onOpenRun(retried.run_id);
              })
            }
          >
            Retry as a new run
          </button>
        )}
      </div>
      {error && <p className="type-meta live-run__error">{error}</p>}
      {failure && (
        <div className="run-section">
          <h3>Failure</h3>
          {typeof failure.failed_node === "string" && <p>{`Failed node: ${failure.failed_node}`}</p>}
          {typeof failure.error === "string" && <p>{`Error: ${maskText(failure.error)}`}</p>}
          {typeof failure.reason === "string" && <p className="type-meta">{`Reason: ${failure.reason}`}</p>}
        </div>
      )}
      <RunSnapshot run={run} />
      {active ? (
        <LiveRunSummary runId={run.run_id} status={status} view={monitor.view} mode={monitor.mode} live={monitor.live} error={monitor.error} />
      ) : (
        <ReplayPanel runId={run.run_id} nodeIds={rows.map((row) => row.nodeId)} fetchImpl={fetchImpl} />
      )}
      <NodeOutcomes rows={rows} wallTimeS={wallTimeS} selected={selectedNode} onSelect={setSelectedNode} />
      {effects.length > 0 && (
        <section className="run-section" aria-label="Completed effects">
          <h3>Completed effects</h3>
          <p className="type-meta">
            {run.status === "succeeded" ? "Sources this run committed." : "Sources committed before the run stopped. They stay committed; a retry starts a new run."}
          </p>
          <ul className="effect-list">
            {effects.map((effect) => (
              <li key={effect}>
                <code>{maskText(effect)}</code>
              </li>
            ))}
          </ul>
        </section>
      )}
      {result?.outputs && (
        <EvidenceInspector outputs={result.outputs} fallbackCollection={collections.length === 1 ? collections[0]! : null} fetchImpl={fetchImpl} />
      )}
    </section>
  );
}
