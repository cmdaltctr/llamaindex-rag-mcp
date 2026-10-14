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
import { useCallback, useMemo, useState, type KeyboardEvent } from "react";
import type { OperationDescriptor, PortRef, ValidationIssue } from "../api/pipelines";
import { checkConnection, connectionGuard, findOperation } from "./connections";
import { edgeKey, moveNode, removeEdge, removeNode, removeSelection, setSelection, setViewport, type Draft } from "./graph";
import { OperationNode, type OperationFlowNode } from "./OperationNode";
import { edgeRunStyle, type NodeRunState } from "../runs/runState";

const NODE_TYPES = { operation: OperationNode };

interface FlowSurfaceProps {
  draft: Draft;
  catalogue: readonly OperationDescriptor[];
  issues: readonly ValidationIssue[];
  onChange: (change: (draft: Draft) => Draft) => void;
  onConnect: (source: PortRef, target: PortRef) => void;
  onRefused: (reason: string) => void;
  /** Node states from the events of the shown run, keyed by the run's own node ids. Absent: no run is shown. */
  runNodes?: { ids: ReadonlySet<string>; states: Readonly<Record<string, NodeRunState>> } | null;
  reducedMotion?: boolean;
}

type Size = { width: number; height: number };

function isTextField(target: EventTarget): boolean {
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
export function FlowSurface({ draft, catalogue, issues, onChange, onConnect, onRefused, runNodes = null, reducedMotion = false }: FlowSurfaceProps) {
  const [measured, setMeasured] = useState<Record<string, Size>>({});
  const selected = useMemo(() => new Set(draft.layout.selection), [draft.layout.selection]);

  const nodes = useMemo<OperationFlowNode[]>(
    () =>
      draft.graph.nodes.map((node) => ({
        id: node.id,
        type: "operation",
        position: draft.layout.positions[node.id] ?? { x: 0, y: 0 },
        selected: selected.has(node.id),
        measured: measured[node.id],
        ariaLabel: `Node ${node.id}, ${node.operation}`,
        data: {
          nodeId: node.id,
          operationId: node.operation,
          operation: findOperation(catalogue, node.operation, node.version),
          enabled: node.enabled !== false,
          issues: issues.filter((issue) => issue.node_id === node.id),
          run: runNodes?.ids.has(node.id) ? { state: runNodes.states[node.id] } : undefined,
        },
      })),
    [draft.graph.nodes, draft.layout.positions, selected, measured, catalogue, issues, runNodes],
  );

  const edges = useMemo<Edge[]>(
    () =>
      draft.graph.edges.map((edge) => {
        const id = edgeKey(edge);
        const live = edgeRunStyle(runNodes?.ids.has(edge.target.node) ? runNodes.states[edge.target.node]?.status : undefined, reducedMotion);
        return {
          id,
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
    [draft.graph.edges, selected, issues, runNodes, reducedMotion],
  );

  const onNodesChange = useCallback(
    (changes: NodeChange<OperationFlowNode>[]) => {
      const sizes = changes.flatMap((c) => (c.type === "dimensions" && c.dimensions ? [[c.id, c.dimensions] as const] : []));
      if (sizes.length > 0) setMeasured((current) => ({ ...current, ...Object.fromEntries(sizes) }));
      const relevant = changes.filter((c) => c.type === "position" || c.type === "select" || c.type === "remove");
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
    [onChange],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      onChange((current) =>
        changes.reduce((next, change) => {
          if (change.type === "select") return setSelection(next, applySelection(next.layout.selection, [change]));
          if (change.type === "remove") return removeEdge(next, change.id);
          return next;
        }, current),
      );
    },
    [onChange],
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      if (!connection.sourceHandle || !connection.targetHandle) return;
      onConnect({ node: connection.source, port: connection.sourceHandle }, { node: connection.target, port: connection.targetHandle });
    },
    [onConnect],
  );

  // A drag that ends on an incompatible handle gets the same explanation as the keyboard menu.
  const handleConnectEnd = useCallback(
    (_: MouseEvent | TouchEvent, state: FinalConnectionState) => {
      const { fromHandle, toHandle } = state;
      if (state.isValid !== false || !fromHandle?.id || !toHandle?.id) return;
      const [out, into] = fromHandle.type === "source" ? [fromHandle, toHandle] : [toHandle, fromHandle];
      const reason = checkConnection(draft, catalogue, { node: out.nodeId, port: out.id! }, { node: into.nodeId, port: into.id! });
      if (reason) onRefused(`Cannot connect: ${reason}`);
    },
    [draft, catalogue, onRefused],
  );

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if ((event.key === "Delete" || event.key === "Backspace") && !isTextField(event.target)) {
      event.preventDefault();
      onChange(removeSelection);
    }
  }

  return (
    <div className="canvas-surface" onKeyDown={handleKeyDown}>
      <ReactFlow<OperationFlowNode>
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={handleConnect}
        onConnectEnd={handleConnectEnd}
        isValidConnection={connectionGuard(draft, catalogue)}
        onMoveEnd={(_, viewport) => onChange((current) => setViewport(current, viewport))}
        defaultViewport={draft.layout.viewport}
        deleteKeyCode={null}
        minZoom={0.25}
      >
        <Background gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
