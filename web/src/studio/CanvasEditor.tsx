import { Workflow } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { OperationDescriptor, PortRef } from "../api/pipelines";
import type { ProfileRecord } from "../api/profiles";
import { ACTIVE_RUN_STATUSES } from "../api/runs";
import { EmptyState } from "../components/EmptyState";
import { useCanvasFullScreen } from "../lib/CanvasFullScreen";
import type { Purpose } from "../lib/routes";
import { useReducedMotion } from "../runs/useReducedMotion";
import { useRecentlyFinished } from "../runs/useRecentlyFinished";
import { useRunMonitor } from "../runs/useRunMonitor";
import { checkConnection } from "./connections";
import { CanvasPanel } from "./CanvasPanel";
import { ConnectionMenu } from "./ConnectionMenu";
import { type FocusRequest } from "./FocusStep";
import { FlowSurface } from "./FlowSurface";
import { addEdge, addNode, setSelection } from "./graph";
import { GraphOutline } from "./GraphOutline";
import { NodeInspector } from "./NodeInspector";
import { Notices } from "./Notices";
import { Palette } from "./Palette";
import { PipelineBar } from "./PipelineBar";
import { ProfileHeader } from "./ProfileHeader";
import { RunPanel } from "./RunPanel";
import { SaveRevisionDialog } from "./SaveRevisionDialog";
import { RunProgress } from "./RunProgress";
import { useCanvasSession, type CanvasSource } from "./useCanvasSession";
import { useFullScreenKeys } from "./useFullScreenKeys";

interface CanvasEditorProps {
  profile: ProfileRecord;
  purpose: Purpose;
  /** A saved pipeline (editable), or the standard graph of a built-in profile (read-only). */
  source: CanvasSource;
  /** Opens the duplicate dialog for a built-in profile. */
  onDuplicate: () => void;
}

/**
 * The canvas sub-page of one pipeline: a slim bar, the flow surface filling the
 * main area, and one floating panel on the right that holds every other
 * control. Mount with `key={pipelineId}` (or a key for the standard graph).
 */
export function CanvasEditor({ profile, purpose, source, onDuplicate }: CanvasEditorProps) {
  const session = useCanvasSession(source);
  const { draft, update, setNotice, run, revision, readOnly } = session;
  const catalogue = session.operations.data ?? [];
  const monitor = useRunMonitor(run?.run_id ?? null);
  const finishedNodes = useRecentlyFinished(monitor.view.nodes, monitor.live);
  // Hidden state resets on every visit: the editor is keyed by pipeline, so a new mount starts shown.
  const [headerHidden, setHeaderHidden] = useState(false);
  const reducedMotion = useReducedMotion();
  const { fullScreen, setFullScreen } = useCanvasFullScreen();
  const exitRef = useRef<HTMLButtonElement>(null);
  const [focusRequest, setFocusRequest] = useState<FocusRequest | null>(null);
  // Picking a step in the panel selects it and centres the canvas on it. A click on the canvas only selects.
  const pickStep = (id: string) => {
    update((current) => setSelection(current, [id]));
    setFocusRequest((current) => ({ id, n: (current?.n ?? 0) + 1 }));
  };
  useFullScreenKeys(exitRef);
  // The toolbar lives in the flow surface, which an empty graph does not show. Without it the user has no exit.
  const emptyGraph = draft.graph.nodes.length === 0;
  // The editor owns the exit button. When it goes away (a profile that fails to load, another route), full screen ends with it.
  useEffect(() => () => setFullScreen(false), [setFullScreen]);
  useEffect(() => {
    if (fullScreen && emptyGraph) setFullScreen(false);
  }, [fullScreen, emptyGraph, setFullScreen]);
  // Events are authoritative once they arrive; until then the run record is shown.
  const runStatus = monitor.refreshedStatus ?? monitor.view.runStatus ?? run?.status ?? null;
  const runNodes = useMemo(
    () => (run && session.runRevision ? { ids: new Set(session.runRevision.document.nodes.map((node) => node.id)), states: monitor.view.nodes } : null),
    [run, session.runRevision, monitor.view.nodes],
  );

  // Counts runs started from the panel, so the panel opens Revision and run for them and not for a run that existed at load.
  const [runStarts, setRunStarts] = useState(0);
  // A profile in use asks first: the save changes how its collections work.
  const [confirmingSave, setConfirmingSave] = useState(false);
  const inUse = readOnly ? [] : profile.used_by;
  const actions = {
    ...session.actions,
    run: () => { setRunStarts((count) => count + 1); return session.actions.run(); },
    saveRevision: () => (inUse.length > 0 ? setConfirmingSave(true) : void session.actions.saveRevision()),
  };

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
        <EmptyState icon={Workflow} message="The graph is empty. Add a step from Operations to start." />
      </div>
    ) : session.operations.isPending ? (
      // Nodes need the catalogue for their ports, so the surface waits for it.
      <p className="p-4 text-meta text-muted-foreground">Loading the catalogue.</p>
    ) : (
      <FlowSurface
        draft={draft}
        catalogue={catalogue}
        issues={session.issues}
        controls={session.controls}
        embeddingModel={profile.kind === "user" ? (profile.embedding?.model ?? session.embeddingModel) : session.embeddingModel}
        onChange={update}
        onConnect={(source, target) => {
          const reason = connect(source, target);
          if (reason) refuse(`Cannot connect: ${reason}`);
        }}
        onRefused={refuse}
        runNodes={runNodes}
        reducedMotion={reducedMotion}
        finishedNodes={finishedNodes}
        readOnly={readOnly}
        focusRequest={focusRequest}
        exitRef={exitRef}
      />
    );

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div hidden={fullScreen} className={fullScreen ? "hidden" : "flex flex-col gap-1 border-b border-border bg-card px-4 py-2"}>
        <ProfileHeader profile={profile} purpose={purpose} onDuplicate={onDuplicate} collapsed={headerHidden} onToggle={() => setHeaderHidden((hidden) => !hidden)} />
        <Notices notice={session.notice} />
      </div>
      <div className="relative flex min-h-0 flex-1 flex-col">
        <div className={fullScreen ? "fixed inset-0 z-50 bg-background" : "h-[50vh] min-h-64 lg:absolute lg:inset-0 lg:h-auto"}>
          {surface}
        </div>
        <CanvasPanel
          fullScreen={fullScreen}
          selectedNode={selectedNode}
          runStarts={runStarts}
          sections={{
            "pipeline-settings": <PipelineBar draft={draft} onChange={update} readOnly={readOnly} />,
            operations: <Palette operations={session.operations.data} error={session.operations.error} onRetry={() => void session.operations.refetch()} onAdd={add} readOnly={readOnly} />,
            nodes: <GraphOutline draft={draft} issues={session.issues} onChange={update} onSelect={pickStep} onAnnounce={announce} readOnly={readOnly} />,
            connect: <ConnectionMenu draft={draft} catalogue={catalogue} onConnect={connect} readOnly={readOnly} />,
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
                onSelectNode={pickStep}
                actions={actions}
                readOnly={readOnly}
                live={
                  run && runStatus ? (
                    <RunProgress runId={run.run_id} status={runStatus} view={monitor.view} mode={monitor.mode} live={monitor.live} error={monitor.error} />
                  ) : null
                }
              />
            ),
            "node-settings": <NodeInspector draft={draft} nodeId={selectedNode} catalogue={catalogue} issues={session.issues} controls={session.controls} onChange={update} readOnly={readOnly} profile={profile} />,
          }}
        />
      </div>
      <SaveRevisionDialog
        purpose={purpose}
        collections={inUse}
        open={confirmingSave}
        onCancel={() => setConfirmingSave(false)}
        onConfirm={() => {
          setConfirmingSave(false);
          void session.actions.saveRevision();
        }}
      />
    </section>
  );
}
