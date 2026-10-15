import { ArrowLeft, Workflow } from "lucide-react";
import { useMemo } from "react";
import type { OperationDescriptor, PipelineRecord, PortRef, RevisionRecord } from "../api/pipelines";
import { ACTIVE_RUN_STATUSES } from "../api/runs";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui/button";
import { formatRoute } from "../lib/routes";
import { useReducedMotion } from "../runs/useReducedMotion";
import { useRunMonitor } from "../runs/useRunMonitor";
import { checkConnection } from "./connections";
import { ConnectionMenu } from "./ConnectionMenu";
import { FlowSurface } from "./FlowSurface";
import { addEdge, addNode, setSelection } from "./graph";
import { GraphOutline } from "./GraphOutline";
import { NodeInspector } from "./NodeInspector";
import { Notices } from "./Notices";
import { Palette } from "./Palette";
import { PipelineBar } from "./PipelineBar";
import { RunPanel } from "./RunPanel";
import { RunProgress } from "./RunProgress";
import { useCanvasSession } from "./useCanvasSession";

interface CanvasEditorProps {
  pipeline: PipelineRecord;
  revision: RevisionRecord | null;
}

/**
 * The canvas sub-page of one pipeline: the flow surface in the main column,
 * the operation palette and the selected node's settings in the right column.
 * Mount with `key={pipelineId}`.
 */
export function CanvasEditor({ pipeline, revision }: CanvasEditorProps) {
  const session = useCanvasSession(pipeline, revision);
  const { draft, update, setNotice, run } = session;
  const catalogue = session.operations.data ?? [];
  const monitor = useRunMonitor(run?.run_id ?? null);
  const reducedMotion = useReducedMotion();
  // Events are authoritative once they arrive; until then the run record is shown.
  const runStatus = monitor.refreshedStatus ?? monitor.view.runStatus ?? run?.status ?? null;
  const runNodes = useMemo(
    () => (run && session.runRevision ? { ids: new Set(session.runRevision.document.nodes.map((node) => node.id)), states: monitor.view.nodes } : null),
    [run, session.runRevision, monitor.view.nodes],
  );

  const announce = (text: string) => setNotice({ kind: "status", text });
  const refuse = (text: string) => setNotice({ kind: "refused", text });

  function add(operation: OperationDescriptor) {
    const nodeId = addNode(draft, operation).nodeId;
    update((current) => addNode(current, operation).draft);
    announce(`Added node ${nodeId} (${operation.operation_id}).`);
  }

  function connect(source: PortRef, target: PortRef): string | null {
    const reason = checkConnection(draft, catalogue, source, target);
    if (reason !== null) return reason;
    update((current) => addEdge(current, { source, target }));
    announce(`Connected ${source.node}.${source.port} to ${target.node}.${target.port}.`);
    return null;
  }

  const nodeIds = new Set(draft.graph.nodes.map((node) => node.id));
  const selectedNode = draft.layout.selection.find((id) => nodeIds.has(id)) ?? null;
  const inputNames = [...new Set([...draft.graph.inputs, ...(revision?.document.inputs ?? [])].map((input) => input.name))];

  return (
    <section>
      <PageHeader
        title={draft.layout.title || pipeline.title}
        summary="Connect pipeline stages, check the graph and run it."
        actions={
          <Button asChild variant="outline">
            <a href={formatRoute({ area: "studio", pipelineId: null })}>
              <ArrowLeft aria-hidden="true" />
              All pipelines
            </a>
          </Button>
        }
      />
      <Notices notice={session.notice} />
      <div className="mt-2 grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex min-w-0 flex-col gap-4">
          <PipelineBar draft={draft} onChange={update} />
          {draft.graph.nodes.length === 0 ? (
            <EmptyState icon={Workflow} message="The graph is empty. Add an operation from the catalogue to start." />
          ) : session.operations.isPending ? (
            // Nodes need the catalogue for their ports, so the surface waits for it.
            <p className="text-meta text-muted-foreground">Loading the catalogue.</p>
          ) : (
            <FlowSurface
              draft={draft}
              catalogue={catalogue}
              issues={session.issues}
              onChange={update}
              onConnect={(source, target) => {
                const reason = connect(source, target);
                if (reason) refuse(`Cannot connect: ${reason}`);
              }}
              onRefused={refuse}
              runNodes={runNodes}
              reducedMotion={reducedMotion}
            />
          )}
          <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-2">
            <GraphOutline draft={draft} issues={session.issues} onChange={update} onAnnounce={announce} />
            <ConnectionMenu draft={draft} catalogue={catalogue} onConnect={connect} />
          </div>
          <RunPanel
            revision={revision}
            dirty={session.dirty}
            busy={session.busy}
            inputNames={inputNames}
            inputValues={session.inputValues}
            onInput={session.setInputValue}
            issues={session.issues}
            run={run ? { record: run, revision: session.runRevision } : null}
            runActive={runStatus !== null && ACTIVE_RUN_STATUSES.has(runStatus)}
            onSelectNode={(id) => update((current) => setSelection(current, [id]))}
            actions={session.actions}
            live={
              run && runStatus ? (
                <RunProgress runId={run.run_id} status={runStatus} view={monitor.view} mode={monitor.mode} live={monitor.live} error={monitor.error} />
              ) : null
            }
          />
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <Palette operations={session.operations.data} error={session.operations.error} onRetry={() => void session.operations.refetch()} onAdd={add} />
          <NodeInspector draft={draft} nodeId={selectedNode} catalogue={catalogue} issues={session.issues} controls={session.controls} onChange={update} />
        </div>
      </div>
    </section>
  );
}
