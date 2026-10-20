/**
 * The canvas draft: an execution graph plus a separate presentation layout.
 *
 * Every function returns a new draft. `toDocument` gives the execution
 * document that a revision stores. `toLayout` gives the layout that
 * `PUT .../layout` stores. Moving a node or changing the viewport or the
 * selection never changes `toDocument`.
 */
import type {
  EdgeSpec,
  GraphDocument,
  GraphInput,
  GraphLayout,
  LayoutDirection,
  GraphOutput,
  JsonValue,
  NodeSpec,
  OperationDescriptor,
  PortRef,
} from "../api/pipelines";

export const SCHEMA_VERSION = 1;

export interface DraftGraph {
  nodes: NodeSpec[];
  edges: EdgeSpec[];
  inputs: GraphInput[];
  outputs: GraphOutput[];
  profile: string | null;
  collection: string | null;
  overrides: Record<string, JsonValue>;
}

export interface DraftLayout {
  positions: Record<string, { x: number; y: number }>;
  viewport: { x: number; y: number; zoom: number };
  selection: string[];
  direction: LayoutDirection;
}

export interface Draft {
  graph: DraftGraph;
  layout: DraftLayout;
}

type Position = { x: number; y: number };

export function emptyDraft(): Draft {
  return {
    graph: { nodes: [], edges: [], inputs: [], outputs: [], profile: null, collection: null, overrides: {} },
    layout: { positions: {}, viewport: { x: 0, y: 0, zoom: 1 }, selection: [], direction: "horizontal" },
  };
}

export function edgeKey(edge: EdgeSpec): string {
  return `${edge.source.node}.${edge.source.port}->${edge.target.node}.${edge.target.port}`;
}

const samePort = (a: PortRef, b: PortRef) => a.node === b.node && a.port === b.port;

function cleanNode(node: NodeSpec): NodeSpec {
  const params = Object.fromEntries(Object.entries(node.params ?? {}).filter(([, value]) => value !== null));
  return {
    id: node.id,
    operation: node.operation,
    ...(node.version != null ? { version: node.version } : {}),
    ...(Object.keys(params).length > 0 ? { params } : {}),
    ...(node.enabled === false ? { enabled: false } : {}),
  };
}

/** Normalises a stored revision (which carries filled-in defaults) and a layout into a draft. */
export function fromDocument(document: GraphDocument | null, layout: GraphLayout): Draft {
  const base = emptyDraft();
  const graph: DraftGraph = document
    ? {
        nodes: document.nodes.map(cleanNode),
        edges: [...(document.edges ?? [])],
        inputs: (document.inputs ?? []).map(({ name, kind, targets, required }) => ({
          name,
          kind,
          targets: [...targets],
          ...(required === false ? { required: false } : {}),
        })),
        outputs: [...(document.outputs ?? [])],
        profile: document.profile ?? null,
        collection: document.collection ?? null,
        overrides: { ...(document.overrides ?? {}) },
      }
    : base.graph;
  return {
    graph,
    layout: {
      positions: { ...(layout.positions ?? {}) },
      viewport: layout.viewport ?? base.layout.viewport,
      selection: [...(layout.selection ?? [])],
      direction: layout.direction ?? "horizontal",
    },
  };
}

export function toDocument(draft: Draft): GraphDocument {
  const { graph } = draft;
  return {
    schema_version: SCHEMA_VERSION,
    nodes: graph.nodes.map(cleanNode),
    ...(graph.edges.length > 0 ? { edges: graph.edges } : {}),
    ...(graph.inputs.length > 0 ? { inputs: graph.inputs } : {}),
    ...(graph.outputs.length > 0 ? { outputs: graph.outputs } : {}),
    ...(graph.profile ? { profile: graph.profile } : {}),
    ...(graph.collection?.trim() ? { collection: graph.collection.trim() } : {}),
    ...(Object.keys(graph.overrides).length > 0 ? { overrides: graph.overrides } : {}),
  };
}

export function toLayout(draft: Draft): GraphLayout {
  const { positions, viewport, selection, direction } = draft.layout;
  return { positions, viewport, selection, direction };
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) => (a < b ? -1 : 1));
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

/** True when two graphs serialise to the same execution document. */
export function sameDocument(a: DraftGraph, b: DraftGraph): boolean {
  const doc = (graph: DraftGraph) => toDocument({ graph, layout: emptyDraft().layout });
  return canonical(doc(a)) === canonical(doc(b));
}

export function withGraph(draft: Draft, graph: Partial<DraftGraph>): Draft {
  return { ...draft, graph: { ...draft.graph, ...graph } };
}

export function withLayout(draft: Draft, layout: Partial<DraftLayout>): Draft {
  return { ...draft, layout: { ...draft.layout, ...layout } };
}

function newNodeId(draft: Draft, operationId: string): string {
  const stem = (operationId.split(".").pop() ?? "node").replace(/[^A-Za-z0-9_-]/g, "_").replace(/^[^A-Za-z]+/, "") || "node";
  const taken = new Set(draft.graph.nodes.map((node) => node.id));
  if (!taken.has(stem)) return stem;
  let index = 2;
  while (taken.has(`${stem}_${index}`)) index += 1;
  return `${stem}_${index}`;
}

/** Returns the first grid slot that no existing node covers. */
function freeSlot(draft: Draft): Position {
  const taken = Object.values(draft.layout.positions);
  for (let index = 0; ; index += 1) {
    const slot = { x: 40 + 260 * (index % 4), y: 40 + 280 * Math.floor(index / 4) };
    if (taken.every((at) => Math.abs(at.x - slot.x) >= 260 || Math.abs(at.y - slot.y) >= 280)) return slot;
  }
}

/** Adds a node for `operation`, selects it, and returns the new identifier. */
export function addNode(draft: Draft, operation: OperationDescriptor, position?: Position): { draft: Draft; nodeId: string } {
  const nodeId = newNodeId(draft, operation.operation_id);
  const at = position ?? freeSlot(draft);
  const node: NodeSpec = { id: nodeId, operation: operation.operation_id, version: operation.version };
  const next = withGraph(draft, { nodes: [...draft.graph.nodes, node] });
  return { draft: withLayout(next, { positions: { ...draft.layout.positions, [nodeId]: at }, selection: [nodeId] }), nodeId };
}

export function removeNode(draft: Draft, nodeId: string): Draft {
  const { graph, layout } = draft;
  const edges = graph.edges.filter((e) => e.source.node !== nodeId && e.target.node !== nodeId);
  const inputs = graph.inputs
    .map((input) => ({ ...input, targets: input.targets.filter((t) => t.node !== nodeId) }))
    .filter((input) => input.targets.length > 0);
  const positions = Object.fromEntries(Object.entries(layout.positions).filter(([id]) => id !== nodeId));
  const removedEdges = new Set(graph.edges.filter((e) => !edges.includes(e)).map(edgeKey));
  return {
    graph: {
      ...graph,
      nodes: graph.nodes.filter((n) => n.id !== nodeId),
      edges,
      inputs,
      outputs: graph.outputs.filter((o) => o.source.node !== nodeId),
    },
    layout: { ...layout, positions, selection: layout.selection.filter((id) => id !== nodeId && !removedEdges.has(id)) },
  };
}

export function addEdge(draft: Draft, edge: EdgeSpec): Draft {
  return withGraph(draft, { edges: [...draft.graph.edges, edge] });
}

export function removeEdge(draft: Draft, key: string): Draft {
  const next = withGraph(draft, { edges: draft.graph.edges.filter((edge) => edgeKey(edge) !== key) });
  return withLayout(next, { selection: draft.layout.selection.filter((id) => id !== key) });
}

function updateNode(draft: Draft, nodeId: string, change: (node: NodeSpec) => NodeSpec): Draft {
  return withGraph(draft, { nodes: draft.graph.nodes.map((node) => (node.id === nodeId ? change(node) : node)) });
}

/** Sets a parameter. `null` or `undefined` removes it, so the value is inherited. */
export function setParam(draft: Draft, nodeId: string, name: string, value: JsonValue | undefined): Draft {
  return updateNode(draft, nodeId, (node) => {
    const params = { ...(node.params ?? {}) };
    if (value === null || value === undefined) delete params[name];
    else params[name] = value;
    return { ...node, params };
  });
}

export function setEnabled(draft: Draft, nodeId: string, enabled: boolean): Draft {
  return updateNode(draft, nodeId, (node) => ({ ...node, enabled }));
}

export function toggleGraphInput(draft: Draft, nodeId: string, port: string, kind: string, on: boolean): Draft {
  const target = { node: nodeId, port };
  const inputs = draft.graph.inputs.map((input) => ({ ...input, targets: input.targets.filter((t) => !samePort(t, target)) }));
  if (on) {
    const shared = inputs.find((input) => input.name === port && input.kind === kind);
    if (shared) shared.targets = [...shared.targets, target];
    else {
      const name = inputs.some((input) => input.name === port) ? `${port}_${nodeId}` : port;
      inputs.push({ name, kind, targets: [target] });
    }
  }
  return withGraph(draft, { inputs: inputs.filter((input) => input.targets.length > 0) });
}

export function toggleGraphOutput(draft: Draft, nodeId: string, port: string, on: boolean): Draft {
  const source = { node: nodeId, port };
  const outputs = draft.graph.outputs.filter((output) => !samePort(output.source, source));
  if (on) outputs.push({ name: outputs.some((o) => o.name === port) ? `${nodeId}_${port}` : port, source });
  return withGraph(draft, { outputs });
}

export function setProfile(draft: Draft, profile: string | null): Draft {
  return withGraph(draft, { profile: profile || null });
}

export function setCollection(draft: Draft, collection: string | null): Draft {
  return withGraph(draft, { collection: collection || null });
}

export function moveNode(draft: Draft, nodeId: string, position: Position): Draft {
  return withLayout(draft, { positions: { ...draft.layout.positions, [nodeId]: position } });
}

/** Replaces the step positions and the direction in one change. The execution graph is untouched. */
export function setArrangement(draft: Draft, positions: Record<string, Position>, direction: LayoutDirection): Draft {
  return withLayout(draft, { positions, direction });
}

export function setViewport(draft: Draft, viewport: DraftLayout["viewport"]): Draft {
  return withLayout(draft, { viewport });
}

export function setSelection(draft: Draft, selection: string[]): Draft {
  return withLayout(draft, { selection });
}

/** Removes every selected node and connection. */
export function removeSelection(draft: Draft): Draft {
  const nodeIds = new Set(draft.graph.nodes.map((node) => node.id));
  return draft.layout.selection.reduce(
    (next, id) => (nodeIds.has(id) ? removeNode(next, id) : removeEdge(next, id)),
    draft,
  );
}
