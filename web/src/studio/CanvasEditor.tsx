import { ArrowLeft, Workflow } from "lucide-react";
import { useMemo, useState } from "react";
import type { OperationDescriptor, PipelineRecord, PortRef, RevisionRecord } from "../api/pipelines";
import { ACTIVE_RUN_STATUSES } from "../api/runs";
import { EmptyState } from "../components/EmptyState";
import { Button } from "../components/ui/button";
import { formatRoute } from "../lib/routes";
import { useReducedMotion } from "../runs/useReducedMotion";
import { useRunMonitor } from "../runs/useRunMonitor";
import { checkConnection } from "./connections";
import { CanvasPanel } from "./CanvasPanel";
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
 * The canvas sub-page of one pipeline: a slim bar, the flow surface filling the
 * main area, and one floating panel on the right that holds every other
 * control. Mount with `key={pipelineId}`.
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

  // Counts runs started from the panel, so the panel opens Revision and run for them and not for a run that existed at load.
  const [runStarts, setRunStarts] = useState(0);
  const actions = { ...session.actions, run: () => { setRunStarts((count) => count + 1); return session.actions.run(); } };

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

  const surface =
    draft.graph.nodes.length === 0 ? (
      <div className="p-4">
        <EmptyState icon={Workflow} message="The graph is empty. Add an operation from the catalogue to start." />
      </div>
    ) : session.operations.isPending ? (
      // Nodes need the catalogue for their ports, so the surface waits for it.
      <p className="p-4 text-meta text-muted-foreground">Loading the catalogue.</p>
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
    );

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border bg-card px-4 py-2">
        <div className="min-w-0">
          <h1 tabIndex={-1} className="text-page-title font-semibold outline-none [overflow-wrap:anywhere]">
            {draft.layout.title || pipeline.title}
          </h1>
          <Notices notice={session.notice} />
        </div>
        <Button asChild variant="outline">
          <a href={formatRoute({ area: "studio", pipelineId: null })}>
            <ArrowLeft aria-hidden="true" />
            All pipelines
          </a>
        </Button>
      </div>
      <div className="relative flex min-h-0 flex-1 flex-col">
        <div className="h-[50vh] min-h-64 lg:absolute lg:inset-0 lg:h-auto">{surface}</div>
        <CanvasPanel
          selectedNode={selectedNode}
          runStarts={runStarts}
          sections={{
            "pipeline-settings": <PipelineBar draft={draft} onChange={update} />,
            operations: <Palette operations={session.operations.data} error={session.operations.error} onRetry={() => void session.operations.refetch()} onAdd={add} />,
            nodes: <GraphOutline draft={draft} issues={session.issues} onChange={update} onAnnounce={announce} />,
            connect: <ConnectionMenu draft={draft} catalogue={catalogue} onConnect={connect} />,
            run: (
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
                actions={actions}
                live={
                  run && runStatus ? (
                    <RunProgress runId={run.run_id} status={runStatus} view={monitor.view} mode={monitor.mode} live={monitor.live} error={monitor.error} />
                  ) : null
                }
              />
            ),
            "node-settings": <NodeInspector draft={draft} nodeId={selectedNode} catalogue={catalogue} issues={session.issues} controls={session.controls} onChange={update} />,
          }}
        />
      </div>
    </section>
  );
}
