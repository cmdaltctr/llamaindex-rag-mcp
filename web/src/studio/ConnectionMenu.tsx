import { useId, useState } from "react";
import type { OperationDescriptor, PortRef } from "../api/pipelines";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { findOperation } from "./connections";
import type { Draft } from "./graph";

interface ConnectionMenuProps {
  draft: Draft;
  catalogue: readonly OperationDescriptor[];
  /** Returns the refusal reason, or `null` when the connection was added. */
  onConnect: (source: PortRef, target: PortRef) => string | null;
  /** A read-only graph cannot take a connection. */
  readOnly?: boolean;
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

function PortSelect({ id, label, placeholder, value, options, onChange }: { id: string; label: string; placeholder: string; value: string; options: Option[]; onChange: (value: string) => void }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id}>
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/** Creates a connection without dragging: choose the source port, then the target port. */
export function ConnectionMenu({ draft, catalogue, onConnect, readOnly = false }: ConnectionMenuProps) {
  const idBase = useId();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [refusal, setRefusal] = useState<string | null>(null);
  const source = decode(from);
  const target = decode(to);

  function connect() {
    if (!source || !target) return;
    const reason = onConnect(source, target);
    setRefusal(reason === null ? null : `Cannot connect: ${reason}`);
    if (reason === null) setTo("");
  }

  if (readOnly) return <p className="text-meta text-muted-foreground">This pipeline is read-only.</p>;

  return (
    <>
      <PortSelect id={`${idBase}-from`} label="From output" placeholder="Choose an output port" value={from} options={portOptions(draft, catalogue, "outputs")} onChange={setFrom} />
      <PortSelect id={`${idBase}-to`} label="To input" placeholder="Choose an input port" value={to} options={portOptions(draft, catalogue, "inputs")} onChange={setTo} />
      <Button disabled={!source || !target} onClick={connect} className="self-start">
        Connect
      </Button>
      {refusal && (
        <p role="alert" className="text-meta text-status-error-label">
          {refusal}
        </p>
      )}
    </>
  );
}
