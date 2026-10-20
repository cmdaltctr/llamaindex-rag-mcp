import {
  Background,
  Controls,
  ReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type FinalConnectionState,
  type NodeChange,
} from "@xyflow/react";
import { useCallback, useMemo, useState, type KeyboardEvent, type Ref } from "react";
import type { EffectiveControl, OperationDescriptor, PortRef, ValidationIssue } from "../api/pipelines";
import { checkConnection, connectionGuard, findOperation } from "./connections";
import { edgeKey, moveNode, removeEdge, removeNode, removeSelection, setSelection, setViewport, type Draft } from "./graph";
import { OperationNode, type OperationFlowNode } from "./OperationNode";
import { FocusStep, type FocusRequest } from "./FocusStep";
import { ViewToolbar } from "./ViewToolbar";
import { StepEditContext, type StepEdit } from "./StepCardSettings";
import { cardLines } from "./stepSummary";
import { edgeRunStyle, type NodeRunState } from "../runs/runState";

const NODE_TYPES = { operation: OperationNode };

interface FlowSurfaceProps {
  draft: Draft;
  catalogue: readonly OperationDescriptor[];
  issues: readonly ValidationIssue[];
  /** Effective control values from the latest check that still matches the draft, keyed by node id. */
  controls?: Record<string, EffectiveControl[]>;
  /** The embedding model the Embed chunks card names, or `null` when it is not known. */
  embeddingModel?: string | null;
  onChange: (change: (draft: Draft) => Draft) => void;
  onConnect: (source: PortRef, target: PortRef) => void;
  onRefused: (reason: string) => void;
  /** Node states from the events of the shown run, keyed by the run's own node ids. Absent: no run is shown. */
  runNodes?: { ids: ReadonlySet<string>; states: Readonly<Record<string, NodeRunState>> } | null;
  reducedMotion?: boolean;
  /** Steps that finished a moment ago in a live run. The edge into each one animates for a short time. */
  finishedNodes?: ReadonlySet<string>;
  /** A read-only graph can be panned, zoomed and selected, never changed. */
  readOnly?: boolean;
  /** Set when the user picks a step in the panel: the view centres on it. */
  focusRequest?: FocusRequest | null;
  /** The X button of canvas full screen lives in the toolbar; this ref lets the editor focus it. */
  exitRef?: Ref<HTMLButtonElement>;
  /** "Open in Step settings" in a card settings panel: selects the step and opens Step settings. */
  onOpenStepSettings?: (nodeId: string) => void;
}

type Size = { width: number; height: number };

const refuseAll = () => false;
const NO_CONTROLS: Record<string, EffectiveControl[]> = {};
const NO_LINES = { summary: "", settings: [], extraSettings: [], moreSettings: 0 };
const NO_PORTS: string[] = [];
const NO_FINISHED: ReadonlySet<string> = new Set();

export function isTextField(target: EventTarget): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName));
}

function applySelection(selection: string[], changes: { id: string; selected: boolean }[]): string[] {
  const next = new Set(selection);
  for (const change of changes) {
    if (change.selected) next.add(change.id);
    else next.delete(change.id);
  }
  return [...next];
}

/** The visual graph editor. Node and edge state live in the draft; this component only translates changes. */
export function FlowSurface({
  draft,
  catalogue,
  issues,
  controls = NO_CONTROLS,
  embeddingModel = null,
  onChange,
  onConnect,
  onRefused,
  runNodes = null,
  reducedMotion = false,
  finishedNodes = NO_FINISHED,
  readOnly = false,
  focusRequest = null,
  exitRef,
  onOpenStepSettings,
}: FlowSurfaceProps) {
  const [measured, setMeasured] = useState<Record<string, Size>>({});
  const selected = useMemo(() => new Set(draft.layout.selection), [draft.layout.selection]);

  const { collection, overrides } = draft.graph;
  const stepEdit = useMemo<StepEdit>(() => ({ draft, controls, onChange, readOnly, onOpenStepSettings }), [draft, controls, onChange, readOnly, onOpenStepSettings]);
  const { edges: graphEdges } = draft.graph;

  // The ports that have an edge, per node. An input and an output of one name are two ports.
  const connectedPorts = useMemo(() => {
    const byNode = new Map<string, string[]>();
    const add = (node: string, key: string) => byNode.set(node, [...(byNode.get(node) ?? []), key]);
    for (const edge of graphEdges) {
      add(edge.source.node, `out:${edge.source.port}`);
      add(edge.target.node, `in:${edge.target.port}`);
    }
    return byNode;
  }, [graphEdges]);

  const nodes = useMemo<OperationFlowNode[]>(() => {
    const operations = draft.graph.nodes.map((node) => findOperation(catalogue, node.operation, node.version));
    const titles = operations.map((operation) => operation?.title ?? "Unknown operation");
    return draft.graph.nodes.map((node, index) => {
      const operation = operations[index];
      const title = titles[index]!;
      const showNodeId = titles.filter((other) => other === title).length > 1;
      const lines = operation ? cardLines(operation, node, controls[node.id], { collection, overrides }) : NO_LINES;
      return {
        id: node.id,
        type: "operation",
        position: draft.layout.positions[node.id] ?? { x: 0, y: 0 },
        selected: selected.has(node.id),
        measured: measured[node.id],
        ariaLabel: showNodeId ? `${title} step, ${node.id}` : `${title} step`,
        data: {
          nodeId: node.id,
          operationId: node.operation,
          operation,
          title,
          showNodeId,
          ...lines,
          connected: connectedPorts.get(node.id) ?? NO_PORTS,
          model: node.operation === "embed.chunks" ? { name: embeddingModel } : undefined,
          enabled: node.enabled !== false,
          direction: draft.layout.direction,
          issues: issues.filter((issue) => issue.node_id === node.id),
          run: runNodes?.ids.has(node.id) ? { state: runNodes.states[node.id] } : undefined,
        },
      };
    });
  }, [draft.graph.nodes, overrides, collection, draft.layout.positions, draft.layout.direction, selected, measured, catalogue, issues, runNodes, controls, embeddingModel, connectedPorts]);

  const edges = useMemo<Edge[]>(
    () =>
      draft.graph.edges.map((edge) => {
        const id = edgeKey(edge);
        const live = edgeRunStyle(runNodes?.ids.has(edge.target.node) ? runNodes.states[edge.target.node]?.status : undefined, reducedMotion, finishedNodes.has(edge.target.node));
        return {
          id,
          // Presentation only: the draft and the saved document hold no line type.
          type: "smoothstep",
          source: edge.source.node,
          sourceHandle: edge.source.port,
          target: edge.target.node,
          targetHandle: edge.target.port,
          selected: selected.has(id),
          ariaLabel: `Connection ${edge.source.node}.${edge.source.port} to ${edge.target.node}.${edge.target.port}`,
          animated: live.animated,
          className: issues.some((issue) => issue.edge === id) ? "flow-edge--invalid" : live.className,
        };
      }),
    [draft.graph.edges, selected, issues, runNodes, reducedMotion, finishedNodes],
  );

  const onNodesChange = useCallback(
    (changes: NodeChange<OperationFlowNode>[]) => {
      const sizes = changes.flatMap((c) => (c.type === "dimensions" && c.dimensions ? [[c.id, c.dimensions] as const] : []));
      if (sizes.length > 0) setMeasured((current) => ({ ...current, ...Object.fromEntries(sizes) }));
      const relevant = changes.filter((c) => c.type === "select" || (!readOnly && (c.type === "position" || c.type === "remove")));
      if (relevant.length === 0) return;
      onChange((current) =>
        relevant.reduce((next, change) => {
          if (change.type === "position" && change.position) return moveNode(next, change.id, change.position);
          if (change.type === "select") return setSelection(next, applySelection(next.layout.selection, [change]));
          if (change.type === "remove") return removeNode(next, change.id);
          return next;
        }, current),
      );
    },
    [onChange, readOnly],
  );

  const onEdgesChange = useCallback(
    (all: EdgeChange[]) => {
      const changes = readOnly ? all.filter((change) => change.type === "select") : all;
      if (changes.length === 0) return;
      onChange((current) =>
        changes.reduce((next, change) => {
          if (change.type === "select") return setSelection(next, applySelection(next.layout.selection, [change]));
          if (change.type === "remove") return removeEdge(next, change.id);
          return next;
        }, current),
      );
    },
    [onChange, readOnly],
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      if (readOnly || !connection.sourceHandle || !connection.targetHandle) return;
      onConnect({ node: connection.source, port: connection.sourceHandle }, { node: connection.target, port: connection.targetHandle });
    },
    [onConnect, readOnly],
  );

  // A drag that ends on an incompatible handle gets the same explanation as the keyboard menu.
  const handleConnectEnd = useCallback(
    (_: MouseEvent | TouchEvent, state: FinalConnectionState) => {
      const { fromHandle, toHandle } = state;
      if (readOnly || state.isValid !== false || !fromHandle?.id || !toHandle?.id) return;
      const [out, into] = fromHandle.type === "source" ? [fromHandle, toHandle] : [toHandle, fromHandle];
      const reason = checkConnection(draft, catalogue, { node: out.nodeId, port: out.id! }, { node: into.nodeId, port: into.id! });
      if (reason) onRefused(`Cannot connect: ${reason}`);
    },
    [draft, catalogue, onRefused, readOnly],
  );

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (!readOnly && (event.key === "Delete" || event.key === "Backspace") && !isTextField(event.target)) {
      event.preventDefault();
      onChange(removeSelection);
    }
  }

  return (
    <StepEditContext.Provider value={stepEdit}>
      <div className="h-full min-h-64 overflow-hidden rounded-panel border border-border" onKeyDown={handleKeyDown}>
        <ReactFlow<OperationFlowNode>
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={handleConnect}
          onConnectEnd={handleConnectEnd}
          isValidConnection={readOnly ? refuseAll : connectionGuard(draft, catalogue)}
          onMoveEnd={(_, viewport) => onChange((current) => setViewport(current, viewport))}
          defaultViewport={draft.layout.viewport}
          deleteKeyCode={null}
          nodesDraggable={!readOnly}
          nodesConnectable={!readOnly}
          minZoom={0.25}
        >
          <Background gap={20} />
          <Controls showInteractive={false} />
          <FocusStep request={focusRequest} reducedMotion={reducedMotion} />
          <ViewToolbar exitRef={exitRef} draft={draft} sizes={measured} onChange={onChange} reducedMotion={reducedMotion} />
        </ReactFlow>
      </div>
    </StepEditContext.Provider>
  );
}
