import { useState } from "react";
import type { OperationDescriptor, PortRef } from "../api/pipelines";
import { findOperation } from "./connections";
import type { Draft } from "./graph";

interface ConnectionMenuProps {
  draft: Draft;
  catalogue: readonly OperationDescriptor[];
  /** Returns the refusal reason, or `null` when the connection was added. */
  onConnect: (source: PortRef, target: PortRef) => string | null;
}

type Option = { value: string; label: string };

const SEPARATOR = "::";
const encode = (ref: PortRef) => `${ref.node}${SEPARATOR}${ref.port}`;

function decode(value: string): PortRef | null {
  const [node, port] = value.split(SEPARATOR);
  return node && port ? { node, port } : null;
}

function portOptions(draft: Draft, catalogue: readonly OperationDescriptor[], side: "inputs" | "outputs"): Option[] {
  return draft.graph.nodes.flatMap((node) => {
    const operation = findOperation(catalogue, node.operation, node.version);
    return (operation?.[side] ?? []).map((port) => ({
      value: encode({ node: node.id, port: port.name }),
      label: `${node.id}.${port.name} (${port.type.kind}${port.cardinality === "many" ? ", many" : ""})`,
    }));
  });
}

/** Creates a connection without dragging: choose the source port, then the target port. */
export function ConnectionMenu({ draft, catalogue, onConnect }: ConnectionMenuProps) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [refusal, setRefusal] = useState<string | null>(null);
  const outputs = portOptions(draft, catalogue, "outputs");
  const inputs = portOptions(draft, catalogue, "inputs");
  const source = decode(from);
  const target = decode(to);

  function connect() {
    if (!source || !target) return;
    const reason = onConnect(source, target);
    setRefusal(reason === null ? null : `Cannot connect: ${reason}`);
    if (reason === null) setTo("");
  }

  return (
    <section className="canvas-panel connect-menu" aria-label="Connect ports">
      <h2 className="text-section-title">Connect ports</h2>
      <label className="field">
        <span className="field__label">From output</span>
        <select className="control control--select" value={from} onChange={(event) => setFrom(event.target.value)}>
          <option value="">Choose an output port</option>
          {outputs.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span className="field__label">To input</span>
        <select className="control control--select" value={to} onChange={(event) => setTo(event.target.value)}>
          <option value="">Choose an input port</option>
          {inputs.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="button button--tinted" disabled={!source || !target} onClick={connect}>
        Connect
      </button>
      {refusal && (
        <p className="canvas-error text-meta" role="alert">
          {refusal}
        </p>
      )}
    </section>
  );
}
