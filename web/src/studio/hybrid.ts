/**
 * The Hybrid retrieval switch of Pipeline settings. Pure draft transforms:
 * turning hybrid on adds a Sparse retrieval step and a Reciprocal rank fusion
 * step with the canonical wiring; turning it off removes them again. The steps
 * and connections come from `hybridShape.json`, which a pytest pins to
 * `src/omrg/pipeline_templates.py` (studio-full-settings, design D1 and D2).
 */
import type { EdgeSpec, GraphOutput, NodeSpec, OperationDescriptor, PortRef } from "../api/pipelines";
import { findOperation } from "./connections";
import { edgeKey, removeNode, withGraph, withLayout, type Draft } from "./graph";
import shape from "./hybridShape.json";

export type HybridState =
  | { kind: "on" }
  | { kind: "off" }
  /** The retrieval steps do not match a shape the switch knows. */
  | { kind: "custom"; on: boolean }
  | { kind: "unavailable"; on: boolean; reason: string };

type Role = keyof typeof shape.steps;
type Ids = Record<Role, string>;

const OPERATION = shape.steps;

const ofOperation = (draft: Draft, role: Role): NodeSpec[] => draft.graph.nodes.filter((node) => node.operation === OPERATION[role]);
const samePort = (a: PortRef, b: PortRef) => a.node === b.node && a.port === b.port;
const port = (ids: Ids, ref: { node: string; port: string }): PortRef => ({ node: ids[ref.node as Role], port: ref.port });
const hasEdge = (draft: Draft, from: PortRef, to: PortRef) => draft.graph.edges.some((edge) => samePort(edge.source, from) && samePort(edge.target, to));
const isOn = (draft: Draft) => ofOperation(draft, "sparse").some((node) => node.enabled !== false);

/** The ids of the four retrieval steps, or `null` when the step count is not one each (two for an off graph). */
function roles(draft: Draft): { ids: Partial<Ids>; on: boolean } | null {
  const found = Object.fromEntries((Object.keys(OPERATION) as Role[]).map((role) => [role, ofOperation(draft, role)])) as Record<Role, NodeSpec[]>;
  if (found.prepare.length !== 1 || found.dense.length !== 1) return null;
  const ids: Partial<Ids> = { prepare: found.prepare[0]!.id, dense: found.dense[0]!.id };
  if (found.sparse.length === 0 && found.fuse.length === 0) return { ids, on: false };
  if (found.sparse.length !== 1 || found.fuse.length !== 1) return null;
  if (found.sparse[0]!.enabled === false || found.fuse[0]!.enabled === false) return null;
  return { ids: { ...ids, sparse: found.sparse[0]!.id, fuse: found.fuse[0]!.id }, on: true };
}

/** True when an on graph has exactly the canonical connections into Sparse retrieval and fusion. */
function canonicalOn(draft: Draft, ids: Ids): boolean {
  const added = shape.edges.map((edge) => ({ source: port(ids, edge.source), target: port(ids, edge.target) }));
  if (!added.every((edge) => hasEdge(draft, edge.source, edge.target))) return false;
  const into = (node: string) => draft.graph.edges.filter((edge) => edge.target.node === node).map(edgeKey).sort();
  const expected = (node: string) => added.filter((edge) => edge.target.node === node).map(edgeKey).sort();
  return [ids.sparse, ids.fuse].every((node) => JSON.stringify(into(node)) === JSON.stringify(expected(node)));
}

function availability(catalogue: readonly OperationDescriptor[]): string | null {
  if (catalogue.length === 0) return null;
  for (const role of shape.added as Role[]) {
    const operation = findOperation(catalogue, OPERATION[role]);
    if (operation === undefined) return `This server does not list the ${OPERATION[role]} step.`;
    if (!operation.available) return operation.unavailable_reasons.join(" ") || `${operation.title} cannot run on this server.`;
  }
  return null;
}

/** Whether hybrid is on, and whether the switch can change it. */
export function hybridState(draft: Draft, catalogue: readonly OperationDescriptor[]): HybridState {
  const found = roles(draft);
  const prepare = found?.ids.prepare;
  const dense = found?.ids.dense;
  const knownOff = found !== null && !found.on && hasEdge(draft, { node: prepare!, port: "query" }, { node: dense!, port: "query" });
  const knownOn = found !== null && found.on && canonicalOn(draft, found.ids as Ids);
  if (!knownOff && !knownOn) return { kind: "custom", on: isOn(draft) };
  const reason = availability(catalogue);
  if (reason !== null) return { kind: "unavailable", on: knownOn, reason };
  return { kind: knownOn ? "on" : "off" };
}

function freeId(taken: Set<string>, stem: string): string {
  if (!taken.has(stem)) return stem;
  let index = 2;
  while (taken.has(`${stem}_${index}`)) index += 1;
  return `${stem}_${index}`;
}

/** Moves every connection and graph output that leaves `from` so that it leaves `to`. */
function moveSource(draft: Draft, from: PortRef, to: PortRef): Draft {
  const edges = draft.graph.edges.map((edge): EdgeSpec => (samePort(edge.source, from) ? { ...edge, source: to } : edge));
  const outputs = draft.graph.outputs.map((output): GraphOutput => (samePort(output.source, from) ? { ...output, source: to } : output));
  return withGraph(draft, { edges, outputs });
}

/**
 * Adds Sparse retrieval and fusion with the canonical connections. Returns the
 * draft unchanged when the graph is not a known off shape. `catalogue` sets
 * the step versions when it is known.
 */
export function enableHybrid(draft: Draft, catalogue: readonly OperationDescriptor[] = []): Draft {
  const found = roles(draft);
  if (found === null || found.on) return draft;
  const taken = new Set(draft.graph.nodes.map((node) => node.id));
  const sparse = freeId(taken, "sparse");
  const ids: Ids = { prepare: found.ids.prepare!, dense: found.ids.dense!, sparse, fuse: freeId(new Set([...taken, sparse]), "fuse") };
  const collection = draft.graph.nodes.find((node) => node.id === ids.dense)?.params?.collection;
  const nodes = (shape.added as Role[]).map((role): NodeSpec => {
    const version = findOperation(catalogue, OPERATION[role])?.version;
    const params = role === "sparse" && collection != null ? { params: { collection } } : {};
    return { id: ids[role], operation: OPERATION[role], ...(version !== undefined ? { version } : {}), ...params };
  });
  const moved = moveSource(draft, port(ids, shape.move.from), port(ids, shape.move.to));
  const edges = shape.edges.map((edge): EdgeSpec => ({ source: port(ids, edge.source), target: port(ids, edge.target) }));
  const next = withGraph(moved, { nodes: [...moved.graph.nodes, ...nodes], edges: [...moved.graph.edges, ...edges] });
  // New steps go beside Dense retrieval, across the flow: below it in a horizontal layout. Arrange tidies the rest.
  const at = draft.layout.positions[ids.dense] ?? { x: 0, y: 0 };
  const step = (n: number) => (draft.layout.direction === "vertical" ? { x: at.x + 280 * n, y: at.y } : { x: at.x, y: at.y + 300 * n });
  return withLayout(next, { positions: { ...next.layout.positions, [ids.sparse]: step(1), [ids.fuse]: step(2) } });
}

/** Removes Sparse retrieval and fusion and reconnects Dense retrieval. Returns the draft unchanged when the shape is not known. */
export function disableHybrid(draft: Draft): Draft {
  const found = roles(draft);
  if (found === null || !found.on || !canonicalOn(draft, found.ids as Ids)) return draft;
  const ids = found.ids as Ids;
  const moved = moveSource(draft, port(ids, shape.move.to), port(ids, shape.move.from));
  return removeNode(removeNode(moved, ids.sparse), ids.fuse);
}
