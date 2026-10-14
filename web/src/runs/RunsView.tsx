import { useCallback, useEffect, useRef, useState } from "react";
import type { FetchLike } from "../api/client";
import { listRuns, RUN_STATUSES, type RunDetailRecord } from "../api/runs";
import { maskText } from "./redact";
import { RunDetail } from "./RunDetail";
import { RunList } from "./RunList";

interface RunsViewProps {
  fetchImpl?: FetchLike;
  /** Moves focus to the heading so screen readers announce the view. */
  focusHeading?: boolean;
}

const LIST_LIMIT = 100;

/** Recorded pipeline runs: a filterable list and the selected run's detail. */
export function RunsView({ fetchImpl, focusHeading = false }: RunsViewProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [status, setStatus] = useState("");
  const [runs, setRuns] = useState<RunDetailRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (focusHeading) headingRef.current?.focus();
  }, [focusHeading]);

  useEffect(() => {
    let live = true;
    listRuns({ statuses: status ? [status] : [], limit: LIST_LIMIT }, { fetchImpl }).then(
      (found) => {
        if (!live) return;
        setRuns(found);
        setError(null);
      },
      (failure: unknown) => live && setError(maskText(failure instanceof Error ? failure.message : String(failure))),
    );
    return () => {
      live = false;
    };
  }, [status, fetchImpl, reload]);

  const refresh = useCallback(() => setReload((count) => count + 1), []);

  return (
    <section className="view" aria-labelledby="view-runs-title">
      <header className="view__header">
        <h1 id="view-runs-title" className="type-page-title" ref={headingRef} tabIndex={-1}>
          Runs
        </h1>
        <p className="type-meta">Pipeline runs, their stages and their results.</p>
      </header>
      <div className="runs-toolbar">
        <label className="field-inline">
          <span className="field-inline__label">Status</span>
          <select className="control control--select" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">All statuses</option>
            {RUN_STATUSES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="button button--ghost" onClick={refresh}>
          Refresh list
        </button>
      </div>
      <div className="runs-layout">
        <RunList runs={runs} error={error} selected={selected} onSelect={setSelected} />
        {selected ? (
          <RunDetail key={selected} runId={selected} fetchImpl={fetchImpl} onChanged={refresh} onOpenRun={setSelected} />
        ) : (
          <div className="empty-state empty-state--compact" data-testid="empty-state">
            <p className="empty-state__title">No run selected</p>
            <p className="type-meta">Select a run to see its admitted snapshot, node outcomes and evidence.</p>
          </div>
        )}
      </div>
    </section>
  );
}
