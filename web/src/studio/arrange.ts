import type { LayoutDirection } from "../api/pipelines";

export interface ArrangeInput {
  nodeIds: string[];
  edges: { source: string; target: string }[];
  direction: LayoutDirection;
  /** Measured node sizes. A node without one gets the default size. */
  sizes: Record<string, { width: number; height: number }>;
}

type Position = { x: number; y: number };

/** The size of a node that React Flow has not measured yet. */
const DEFAULT_SIZE = { width: 220, height: 96 };
/** Space between two layers, and between two nodes of one layer. */
const LAYER_GAP = 80;
const NODE_GAP = 40;

/**
 * Each node's layer is the longest path to it from a node with no incoming edge.
 * A graph with a cycle has no such order, so every node falls back to layer 0 in
 * input order. Edges that name an unknown node are ignored.
 */
function layerOf(nodeIds: string[], edges: ArrangeInput["edges"]): Map<string, number> {
  const known = new Set(nodeIds);
  const incoming = new Map<string, string[]>(nodeIds.map((id) => [id, []]));
  const outgoing = new Map<string, string[]>(nodeIds.map((id) => [id, []]));
  for (const { source, target } of edges) {
    if (!known.has(source) || !known.has(target)) continue;
    incoming.get(target)!.push(source);
    outgoing.get(source)!.push(target);
  }
  const waiting = new Map(nodeIds.map((id) => [id, incoming.get(id)!.length]));
  const layers = new Map<string, number>(nodeIds.map((id) => [id, 0]));
  const queue = nodeIds.filter((id) => waiting.get(id) === 0);
  let done = 0;
  while (queue.length > 0) {
    const id = queue.shift()!;
    done += 1;
    for (const next of outgoing.get(id)!) {
      layers.set(next, Math.max(layers.get(next)!, layers.get(id)! + 1));
      waiting.set(next, waiting.get(next)! - 1);
      if (waiting.get(next) === 0) queue.push(next);
    }
  }
  return done === nodeIds.length ? layers : new Map(nodeIds.map((id) => [id, 0]));
}

/**
 * A layered layout, written by hand (design D9). Layers run along the main axis
 * (left to right when horizontal, top to bottom when vertical). The nodes of a
 * layer stack across it in input order, and each layer is centred on the longest one.
 */
export function arrangeLayout({ nodeIds, edges, direction, sizes }: ArrangeInput): Record<string, Position> {
  const layers = layerOf(nodeIds, edges);
  const horizontal = direction === "horizontal";
  const along = (id: string) => (horizontal ? (sizes[id] ?? DEFAULT_SIZE).width : (sizes[id] ?? DEFAULT_SIZE).height);
  const across = (id: string) => (horizontal ? (sizes[id] ?? DEFAULT_SIZE).height : (sizes[id] ?? DEFAULT_SIZE).width);

  const columns: string[][] = [];
  for (const id of nodeIds) (columns[layers.get(id)!] ??= []).push(id);
  const extent = (column: string[]) => column.reduce((sum, id) => sum + across(id), 0) + NODE_GAP * Math.max(0, column.length - 1);
  const tallest = Math.max(0, ...columns.filter(Boolean).map(extent));

  const positions: Record<string, Position> = {};
  let main = 0;
  for (const column of columns) {
    if (column === undefined) continue;
    let cross = (tallest - extent(column)) / 2;
    for (const id of column) {
      positions[id] = horizontal ? { x: main, y: cross } : { x: cross, y: main };
      cross += across(id) + NODE_GAP;
    }
    main += Math.max(...column.map(along)) + LAYER_GAP;
  }
  return positions;
}
