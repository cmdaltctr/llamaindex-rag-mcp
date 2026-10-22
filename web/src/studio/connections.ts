/**
 * Client-side connection checks for quick feedback on the canvas.
 *
 * `portCompatibility` follows `check_port_compatibility` in
 * `src/omrs/core/pipelines/ports.py`. Server validation stays authoritative:
 * it also follows bypassed nodes and host capabilities, which this file does not.
 */
import type { OperationDescriptor, PortRef, PortType } from "../api/pipelines";
import type { Draft } from "./graph";

/** Returns plain-English reasons why `produced` cannot feed `required`. Empty means compatible. */
export function portCompatibility(produced: PortType, required: PortType): string[] {
  if (produced.kind !== required.kind) return [`a '${produced.kind}' value cannot feed a '${required.kind}' input`];
  const reasons: string[] = [];
  const missing = required.provenance.filter((p) => !produced.provenance.includes(p)).sort();
  if (missing.length > 0) reasons.push(`the value does not carry the required provenance: ${missing.join(", ")}`);
  if (required.score_kinds !== null) {
    const accepted = [...required.score_kinds].sort().join(", ");
    if (produced.score_kinds === null) reasons.push(`the output declares no score kind; the input accepts only ${accepted}`);
    else {
      const extra = produced.score_kinds.filter((kind) => !required.score_kinds!.includes(kind)).sort();
      if (extra.length > 0) reasons.push(`score kind ${extra.join(", ")} is not accepted; the input accepts only ${accepted}`);
    }
  }
  if (required.embedding_identity && !produced.embedding_identity) {
    reasons.push("the input needs values bound to the host embedding model");
  }
  const lost = required.reader_declarations.filter((d) => !produced.reader_declarations.includes(d)).sort();
  if (lost.length > 0) reasons.push(`reader declarations are not preserved: ${lost.join(", ")}`);
  return reasons;
}

export function findOperation(
  catalogue: readonly OperationDescriptor[],
  operationId: string,
  version?: number | null,
): OperationDescriptor | undefined {
  const matches = catalogue.filter((op) => op.operation_id === operationId);
  if (version != null) return matches.find((op) => op.version === version);
  return matches.reduce<OperationDescriptor | undefined>((best, op) => (best && best.version > op.version ? best : op), undefined);
}

function operationOf(draft: Draft, catalogue: readonly OperationDescriptor[], nodeId: string) {
  const node = draft.graph.nodes.find((candidate) => candidate.id === nodeId);
  return node ? findOperation(catalogue, node.operation, node.version) : undefined;
}

/** True when `to` can be reached from `from` by following connections. */
function reaches(draft: Draft, from: string, to: string): boolean {
  const seen = new Set<string>();
  const queue = [from];
  while (queue.length > 0) {
    const current = queue.shift()!;
    if (current === to) return true;
    if (seen.has(current)) continue;
    seen.add(current);
    for (const edge of draft.graph.edges) if (edge.source.node === current) queue.push(edge.target.node);
  }
  return false;
}

/** Returns why `source` cannot connect to `target`, or `null` when the connection is allowed. */
export function checkConnection(
  draft: Draft,
  catalogue: readonly OperationDescriptor[],
  source: PortRef,
  target: PortRef,
): string | null {
  const from = `${source.node}.${source.port}`;
  const to = `${target.node}.${target.port}`;
  const producer = operationOf(draft, catalogue, source.node);
  const consumer = operationOf(draft, catalogue, target.node);
  if (!producer || !consumer) return "One of the nodes has an operation that the catalogue does not list.";
  const output = producer.outputs.find((port) => port.name === source.port);
  const input = consumer.inputs.find((port) => port.name === target.port);
  if (!output) return `Node '${source.node}' has no output called '${source.port}'.`;
  if (!input) return `Node '${target.node}' has no input called '${target.port}'.`;
  if (source.node === target.node) return "A node cannot connect to itself.";
  const into = draft.graph.edges.filter((e) => e.target.node === target.node && e.target.port === target.port);
  if (into.some((e) => e.source.node === source.node && e.source.port === source.port)) {
    return `${from} and ${to} are already connected.`;
  }
  const reasons = portCompatibility(output.type, input.type);
  if (reasons.length > 0) return `${from} cannot feed ${to}: ${reasons.join("; ")}.`;
  if (input.cardinality !== "many" && into.length > 0) {
    return `${to} accepts one connection. Remove the existing connection first, or add a combine node.`;
  }
  if (reaches(draft, target.node, source.node)) return `Connecting ${from} to ${to} would create a loop.`;
  return null;
}

export interface FlowConnection {
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
}

/** Adapts `checkConnection` to React Flow's `isValidConnection`. */
export function connectionGuard(draft: Draft, catalogue: readonly OperationDescriptor[]) {
  return (connection: FlowConnection): boolean => {
    if (!connection.sourceHandle || !connection.targetHandle) return false;
    const source = { node: connection.source, port: connection.sourceHandle };
    const target = { node: connection.target, port: connection.targetHandle };
    return checkConnection(draft, catalogue, source, target) === null;
  };
}
