import type { ReactNode } from "react";
import type { RunDetailRecord } from "../../api/runs";
import { Panel } from "../Panel";
import { OutputCut } from "./OutputViewer";
import { SafeValue } from "./SafeValue";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="contents">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 [overflow-wrap:anywhere]">{children}</dd>
    </div>
  );
}

function Code({ children }: { children: string }) {
  return (
    <code dir="ltr" className="font-mono text-code">
      {children}
    </code>
  );
}

/** One folded part of the snapshot. A value cut for display offers its full output below the fold. */
function Fold({ title, open = false, runId, name, value }: { title: string; open?: boolean; runId: string; name: string; value: unknown }) {
  return (
    <div className="flex flex-col gap-2">
      <details open={open} className="rounded-small border border-border px-3 py-2">
        <summary className="cursor-pointer text-ui font-medium">{title}</summary>
        <div className="pt-2">
          <SafeValue value={value} />
        </div>
      </details>
      <OutputCut runId={runId} name={name} value={value} />
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
    <Panel title="Admitted snapshot" description="Recorded at admission. Later draft or profile changes do not alter it." level={3}>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-meta">
        <Field label="Revision">
          <Code>{run.revision_id}</Code>
        </Field>
        <Field label="Graph hash">
          <Code>{run.graph_hash}</Code>
        </Field>
        <Field label="Graph identity">{typeof identity === "string" ? <Code>{identity}</Code> : <span className="text-muted-foreground">not recorded</span>}</Field>
        <Field label="Created">{run.created_at}</Field>
        <Field label="Started">{run.started_at ?? "not started"}</Field>
        <Field label="Finished">{run.finished_at ?? "not finished"}</Field>
      </dl>
      <Fold title="Operation versions" open runId={run.run_id} name="operations" value={operations ?? {}} />
      <Fold title="Resources" runId={run.run_id} name="resources" value={resources} />
      <Fold title="Effective settings (redacted by the server)" open runId={run.run_id} name="settings" value={run.settings} />
      <Fold title="Inputs" open runId={run.run_id} name="inputs" value={run.inputs} />
    </Panel>
  );
}
