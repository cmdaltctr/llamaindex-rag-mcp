import type { ReactNode } from "react";
import type { RunDetailRecord } from "../api/runs";
import { SafeValue } from "./SafeValue";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="safe-value__entry">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/**
 * The run as admitted: revision, graph identity, operation versions, redacted
 * settings and inputs. It comes from the run record only, never from the
 * current draft or profile.
 */
export function RunSnapshot({ run }: { run: RunDetailRecord }) {
  const { graph_identity: identity, operations, ...resources } = run.resources;
  return (
    <section className="run-section" aria-label="Admitted snapshot">
      <h3 className="text-subsection-title">Admitted snapshot</h3>
      <p className="text-meta">Recorded at admission. Later draft or profile changes do not alter it.</p>
      <dl className="safe-value">
        <Field label="Revision">
          <code>{run.revision_id}</code>
        </Field>
        <Field label="Graph hash">
          <code>{run.graph_hash}</code>
        </Field>
        <Field label="Graph identity">{typeof identity === "string" ? <code>{identity}</code> : <span className="text-meta">not recorded</span>}</Field>
        <Field label="Created">{run.created_at}</Field>
        <Field label="Started">{run.started_at ?? "not started"}</Field>
        <Field label="Finished">{run.finished_at ?? "not finished"}</Field>
      </dl>
      <details open>
        <summary>Operation versions</summary>
        <SafeValue value={operations ?? {}} />
      </details>
      <details>
        <summary>Resources</summary>
        <SafeValue value={resources} />
      </details>
      <details open>
        <summary>Effective settings (redacted by the server)</summary>
        <SafeValue value={run.settings} />
      </details>
      <details open>
        <summary>Inputs</summary>
        <SafeValue value={run.inputs} />
      </details>
    </section>
  );
}
