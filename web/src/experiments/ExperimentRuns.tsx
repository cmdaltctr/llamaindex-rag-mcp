import type { FetchLike } from "../api/client";
import { listRuns, type RunDetailRecord } from "../api/runs";
import { ErrorNotice } from "../views/shared/controls";
import { useLoad } from "../views/shared/useLoad";

interface ExperimentRunsProps {
  fetchImpl?: FetchLike;
  /** Context id to display name. */
  names: Record<string, string>;
}

interface ExperimentResource {
  context_id?: unknown;
  /** Backend provenance recorded at admission; it holds the index identity. */
  backend?: { index_identity?: unknown } | null;
}

function experimentOf(run: RunDetailRecord): ExperimentResource | null {
  const value = run.resources?.experiment;
  return typeof value === "object" && value !== null ? (value as ExperimentResource) : null;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "Not recorded";
}

/** Runs admitted in an experiment context. Details open in the Runs view. */
export function ExperimentRuns({ fetchImpl, names }: ExperimentRunsProps) {
  const runs = useLoad(() => listRuns({ limit: 100 }, { fetchImpl }), "experiment-runs");
  const rows = (runs.data ?? []).filter((run) => typeof experimentOf(run)?.context_id === "string");

  return (
    <section className="panel" aria-labelledby="experiments-runs">
      <div className="panel__header">
        <h2 id="experiments-runs" className="type-section-title">
          Experiment runs
        </h2>
        <div className="button-row">
          <button type="button" className="button button--small button--ghost" onClick={runs.reload}>
            Refresh
          </button>
          <a className="button button--small button--tinted" href="#/runs">
            Open the Runs view
          </a>
        </div>
      </div>
      <ErrorNotice message={runs.error === null ? null : `Could not load runs: ${runs.error}`} />
      {runs.data !== undefined && rows.length === 0 ? (
        <p className="type-meta">No experiment runs yet. A notebook run with a bound credential appears here.</p>
      ) : null}
      {rows.length > 0 ? (
        <div className="table-scroll">
          <table className="data-table" aria-label="Experiment runs">
            <thead>
              <tr>
                <th scope="col">Run</th>
                <th scope="col">Status</th>
                <th scope="col">Context</th>
                <th scope="col">Index identity</th>
                <th scope="col">Created</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((run) => {
                const experiment = experimentOf(run)!;
                const contextId = text(experiment.context_id);
                return (
                  <tr key={run.run_id}>
                    <td className="type-code">{run.run_id}</td>
                    <td>{run.status}</td>
                    <td>{names[contextId] ?? contextId}</td>
                    <td className="type-code">{text(experiment.backend?.index_identity)}</td>
                    <td>{run.created_at}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
