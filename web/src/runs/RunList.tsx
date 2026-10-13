import type { RunDetailRecord } from "../api/runs";

interface RunListProps {
  runs: RunDetailRecord[] | null;
  error: string | null;
  selected: string | null;
  onSelect: (runId: string) => void;
}

/** Runs, newest first, as the server lists them. */
export function RunList({ runs, error, selected, onSelect }: RunListProps) {
  if (error) return <p className="text-meta">{`Could not load runs: ${error}`}</p>;
  if (runs === null) return <p className="text-meta">Loading runs.</p>;
  if (runs.length === 0) {
    return (
      <div className="empty-state empty-state--compact">
        <p className="empty-state__title">No runs match this filter</p>
        <p className="text-meta">Each pipeline run is recorded here with its saved revision and events.</p>
      </div>
    );
  }
  return (
    <ul className="run-list" aria-label="Runs">
      {runs.map((run) => (
        <li key={run.run_id}>
          <button
            type="button"
            className="button run-list__item"
            aria-pressed={run.run_id === selected}
            aria-label={`Run ${run.run_id}, ${run.status}, created ${run.created_at}`}
            onClick={() => onSelect(run.run_id)}
          >
            <code>{run.run_id}</code>
            <span className="text-meta">{`${run.status}, ${run.created_at}`}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
