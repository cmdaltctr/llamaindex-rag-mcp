import type { ReactNode } from "react";
import type { RevisionRecord, ValidationIssue } from "../api/pipelines";
import type { SubmittedRun } from "./storage";

interface RunPanelProps {
  revision: RevisionRecord | null;
  dirty: boolean;
  busy: boolean;
  inputNames: string[];
  inputValues: Record<string, string>;
  onInput: (name: string, value: string) => void;
  issues: readonly ValidationIssue[];
  run: SubmittedRun | null;
  runActive: boolean;
  onSelectNode: (nodeId: string) => void;
  actions: { saveLayout: () => void; saveRevision: () => void; validate: () => void; run: () => void; cancel: () => void; refresh: () => void };
  /** Event-driven run progress, shown inside the submitted run. */
  live?: ReactNode;
}

function RevisionState({ revision, dirty }: { revision: RevisionRecord | null; dirty: boolean }) {
  if (!revision) return <p className="type-meta">No saved revision. Save a revision before you run.</p>;
  const number = revision.revision_number;
  if (!dirty) return <p className="type-meta">The draft matches revision {number}.</p>;
  return (
    <p className="canvas-warning type-meta">
      The draft differs from revision {number}. Run uses revision {number} until you save a new revision.
    </p>
  );
}

/** The submitted run as the server admitted it. Draft edits never reach this view. */
function SubmittedRunView({ run, active, busy, onCancel, onRefresh, live }: { run: SubmittedRun; active: boolean; busy: boolean; onCancel: () => void; onRefresh: () => void; live?: ReactNode }) {
  return (
    <section className="submitted-run" aria-label="Submitted run">
      <h3>
        Run <code>{run.runId}</code>: {run.status}
      </h3>
      <p className="type-meta">
        Revision {run.revisionNumber} (<code>{run.revisionId}</code>)
      </p>
      {live}
      <div className="canvas-actions">
        <button type="button" className="button" disabled={busy || !active} onClick={onCancel}>
          Cancel run
        </button>
        <button type="button" className="button button--ghost" disabled={busy} onClick={onRefresh}>
          Refresh status
        </button>
      </div>
      <details>
        <summary>Submitted graph</summary>
        <pre className="submitted-run__document">{JSON.stringify(run.document, null, 2)}</pre>
      </details>
    </section>
  );
}

/** Save, validate, run and cancel controls. */
export function RunPanel(props: RunPanelProps) {
  const { revision, dirty, busy, inputNames, inputValues, issues, run, actions } = props;
  return (
    <section className="canvas-panel run-panel" aria-label="Revision and run">
      <h2 className="type-section-title">Revision and run</h2>
      <div className="canvas-actions">
        <button type="button" className="button" disabled={busy} onClick={actions.saveLayout}>
          Save layout
        </button>
        <button type="button" className="button" disabled={busy} onClick={actions.saveRevision}>
          Save revision
        </button>
        <button type="button" className="button" disabled={busy} onClick={actions.validate}>
          Validate
        </button>
        <button type="button" className="button button--tinted" disabled={busy || !revision} onClick={actions.run}>
          Run
        </button>
      </div>
      <RevisionState revision={revision} dirty={dirty} />
      {inputNames.map((name) => (
        <label key={name} className="field">
          <span className="field__label">{`Input ${name}`}</span>
          <input className="control" value={inputValues[name] ?? ""} onChange={(event) => props.onInput(name, event.target.value)} />
        </label>
      ))}
      {issues.length > 0 && (
        <>
          <h3>Validation issues</h3>
          <ul className="issue-list">
            {issues.map((issue, index) => (
              <li key={index} className="type-meta">
                <code>{issue.code}</code> {issue.message}
                {issue.node_id && (
                  <button type="button" className="button button--ghost button--small" onClick={() => props.onSelectNode(issue.node_id!)}>
                    {`Select node ${issue.node_id}${issue.port ? `, port ${issue.port}` : ""}`}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {run && <SubmittedRunView run={run} active={props.runActive} busy={busy} onCancel={actions.cancel} onRefresh={actions.refresh} live={props.live} />}
    </section>
  );
}
