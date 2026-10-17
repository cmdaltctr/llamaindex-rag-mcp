import type { ReactNode } from "react";
import type { RevisionRecord, ValidationIssue } from "../api/pipelines";
import type { RunDetailRecord } from "../api/runs";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { READ_ONLY_RUN_LINE } from "./profileCopy";

interface RunPanelProps {
  revision: RevisionRecord | null;
  dirty: boolean;
  busy: boolean;
  inputNames: string[];
  inputValues: Record<string, string>;
  onInput: (name: string, value: string) => void;
  issues: readonly ValidationIssue[];
  /** The latest run of the pipeline as the server holds it, with the revision it ran. */
  run: { record: RunDetailRecord; revision: RevisionRecord | null } | null;
  runActive: boolean;
  onSelectNode: (nodeId: string) => void;
  actions: { saveLayout: () => void; saveRevision: () => void; validate: () => void; run: () => void; cancel: () => void; refresh: () => void };
  /** Event-driven run progress, shown inside the latest run. */
  live?: ReactNode;
  /** A built-in profile: Validate stays; saving and running are not offered. */
  readOnly?: boolean;
}

function RevisionState({ revision, dirty }: { revision: RevisionRecord | null; dirty: boolean }) {
  if (!revision) return <p className="text-meta text-muted-foreground">No saved revision. Save a revision before you run.</p>;
  const number = revision.revision_number;
  if (!dirty) return <p className="text-meta text-muted-foreground">The draft matches revision {number}.</p>;
  return (
    <p className="text-meta text-status-warning-label">
      The draft differs from revision {number}. Run uses revision {number} until you save a new revision.
    </p>
  );
}

/** The latest run as the server admitted it. Draft edits never reach this view. */
function LatestRun({ run, active, busy, onCancel, onRefresh, live }: { run: NonNullable<RunPanelProps["run"]>; active: boolean; busy: boolean; onCancel: () => void; onRefresh: () => void; live?: ReactNode }) {
  return (
    <section aria-label="Latest run" className="flex flex-col gap-2 border-t border-border pt-3">
      <h3 className="text-subsection-title font-semibold">Latest run</h3>
      <p className="text-meta text-muted-foreground">
        {run.revision ? `Revision ${run.revision.revision_number}` : "Revision"} (<code className="font-mono text-code">{run.record.revision_id}</code>)
      </p>
      {live}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" disabled={busy || !active} onClick={onCancel}>
          Cancel run
        </Button>
        <Button variant="ghost" disabled={busy} onClick={onRefresh}>
          Refresh status
        </Button>
      </div>
      {run.revision && (
        <details>
          <summary className="cursor-pointer text-ui">Submitted graph</summary>
          <pre className="mt-2 max-h-64 overflow-auto rounded-control bg-muted p-2 font-mono text-code">{JSON.stringify(run.revision.document, null, 2)}</pre>
        </details>
      )}
    </section>
  );
}

/** Save, validate, run and cancel controls. */
export function RunPanel(props: RunPanelProps) {
  const { revision, dirty, busy, inputNames, inputValues, issues, run, actions, readOnly = false } = props;
  return (
    <>
      <div className="flex flex-wrap gap-2">
        {!readOnly && (
          <>
            <Button variant="outline" disabled={busy} onClick={actions.saveLayout}>
              Save layout
            </Button>
            <Button variant="outline" disabled={busy} onClick={actions.saveRevision}>
              Save revision
            </Button>
          </>
        )}
        <Button variant="outline" disabled={busy} onClick={actions.validate}>
          Validate
        </Button>
        {!readOnly && (
          <Button disabled={busy || !revision} onClick={actions.run}>
            Run
          </Button>
        )}
      </div>
      {readOnly ? <p className="text-meta text-muted-foreground">{READ_ONLY_RUN_LINE}</p> : <RevisionState revision={revision} dirty={dirty} />}
      {inputNames.map((name) => (
        <div key={name} className="flex flex-col gap-1.5">
          <Label htmlFor={`run-input-${name}`}>{`Input ${name}`}</Label>
          <Input id={`run-input-${name}`} value={inputValues[name] ?? ""} onChange={(event) => props.onInput(name, event.target.value)} />
        </div>
      ))}
      {issues.length > 0 && (
        <>
          <h3 className="text-subsection-title font-semibold">Validation issues</h3>
          <ul className="flex flex-col gap-2">
            {issues.map((issue, index) => (
              <li key={index} className="flex flex-wrap items-center gap-2 text-meta">
                <span>
                  <code className="font-mono text-code">{issue.code}</code> {issue.message}
                </span>
                {issue.node_id && (
                  <Button variant="ghost" size="xs" onClick={() => props.onSelectNode(issue.node_id!)}>
                    {`Select node ${issue.node_id}${issue.port ? `, port ${issue.port}` : ""}`}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {run && <LatestRun run={run} active={props.runActive} busy={busy} onCancel={actions.cancel} onRefresh={actions.refresh} live={props.live} />}
    </>
  );
}
