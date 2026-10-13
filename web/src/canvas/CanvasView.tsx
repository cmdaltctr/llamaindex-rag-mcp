import { useCallback, useEffect, useMemo, useRef } from "react";
import type { FetchLike } from "../api/client";
import type { OperationDescriptor, PortRef } from "../api/pipelines";
import "./canvas.css";
import { checkConnection } from "./connections";
import { ConnectionMenu } from "./ConnectionMenu";
import { FlowSurface } from "./FlowSurface";
import { addEdge, addNode, setSelection } from "./graph";
import { GraphOutline } from "./GraphOutline";
import { NodeInspector } from "./NodeInspector";
import { Palette } from "./Palette";
import { PipelineBar } from "./PipelineBar";
import { RunPanel } from "./RunPanel";
import { TemplatePicker } from "./TemplatePicker";
import { templateDraft } from "./templates";
import { useCanvasSession } from "./useCanvasSession";
import { ACTIVE_RUN_STATUSES } from "../api/runs";
import { LiveRunSummary } from "../runs/LiveRunSummary";
import { useReducedMotion } from "../runs/useReducedMotion";
import { useRunMonitor } from "../runs/useRunMonitor";

interface CanvasViewProps {
  fetchImpl?: FetchLike;
  /** Moves focus to the heading so screen readers announce the view. */
  focusHeading?: boolean;
}

/** The pipeline canvas: catalogue, graph editor, node settings and run controls. */
export function CanvasView({ fetchImpl, focusHeading = false }: CanvasViewProps) {
  const session = useCanvasSession(fetchImpl);
  const { draft, update, setNotice } = session;
  const catalogue = session.operations ?? [];
  const submitted = session.run;
  const monitor = useRunMonitor(submitted?.runId ?? null, { fetchImpl });
  const reducedMotion = useReducedMotion();
  // Events are authoritative once they arrive; until then the submission response is shown.
  const runStatus = monitor.refreshedStatus ?? monitor.view.runStatus ?? submitted?.status ?? null;
  const runNodes = useMemo(
    () => (submitted ? { ids: new Set(submitted.document.nodes.map((node) => node.id)), states: monitor.view.nodes } : null),
    [submitted, monitor.view.nodes],
  );
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (focusHeading) headingRef.current?.focus();
  }, [focusHeading]);

  const announce = useCallback((text: string) => setNotice({ kind: "status", text }), [setNotice]);
  const refuse = useCallback((text: string) => setNotice({ kind: "error", text }), [setNotice]);

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
  const inputNames = [
    ...new Set([...draft.graph.inputs, ...(session.revision?.document.inputs ?? [])].map((input) => input.name)),
  ];

  return (
    <section className="view canvas-view" aria-labelledby="view-canvas-title">
      <header className="view__header">
        <h1 id="view-canvas-title" className="text-page-title" ref={headingRef} tabIndex={-1}>
          Canvas
        </h1>
        <p className="text-meta">Connect pipeline stages, check the graph and run it.</p>
      </header>
      <PipelineBar
        pipelines={session.pipelines}
        pipelineId={session.pipelineId}
        draft={draft}
        disabled={session.busy}
        onOpen={session.openPipeline}
        onChange={update}
      />
      <TemplatePicker
        fetchImpl={fetchImpl}
        disabled={session.busy}
        replacesWork={session.pipelineId === null && draft.graph.nodes.length > 0}
        onStart={(template) => {
          session.startDraft(templateDraft(template));
          announce(`Started a new draft from the ${template.title} template. Save it as a revision before a run.`);
        }}
      />
      <p className={`canvas-notice canvas-notice--${session.notice?.kind ?? "status"}`} role="status">
        {session.notice?.kind === "status" ? session.notice.text : ""}
      </p>
      {session.notice?.kind === "error" && (
        <p className="canvas-notice canvas-notice--error" role="alert">
          {session.notice.text}
        </p>
      )}
      <div className="canvas-layout">
        <Palette operations={session.operations} error={session.catalogueError} onAdd={add} />
        <div className="canvas-main">
          {draft.graph.nodes.length === 0 ? (
            <div className="empty-state canvas-empty" data-testid="empty-state">
              <p className="empty-state__title">The graph is empty</p>
              <p className="text-meta">Start from an empty graph: add an operation from the catalogue.</p>
            </div>
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
          <GraphOutline draft={draft} issues={session.issues} onChange={update} onAnnounce={announce} />
          <ConnectionMenu draft={draft} catalogue={catalogue} onConnect={connect} />
        </div>
        <div className="canvas-side">
          <NodeInspector
            draft={draft}
            nodeId={selectedNode}
            catalogue={catalogue}
            issues={session.issues}
            controls={session.controls}
            onChange={update}
          />
          <RunPanel
            revision={session.revision}
            dirty={session.dirty}
            busy={session.busy}
            inputNames={inputNames}
            inputValues={session.inputValues}
            onInput={session.setInputValue}
            issues={session.issues}
            run={submitted && runStatus ? { ...submitted, status: runStatus } : submitted}
            runActive={runStatus !== null && ACTIVE_RUN_STATUSES.has(runStatus)}
            onSelectNode={(id) => update((current) => setSelection(current, [id]))}
            actions={session.actions}
            live={
              submitted && runStatus ? (
                <LiveRunSummary
                  runId={submitted.runId}
                  status={runStatus}
                  view={monitor.view}
                  mode={monitor.mode}
                  live={monitor.live}
                  error={monitor.error}
                />
              ) : null
            }
          />
        </div>
      </div>
    </section>
  );
}
