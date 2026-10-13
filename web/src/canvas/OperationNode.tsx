import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import type { OperationDescriptor, PortDescriptor, ValidationIssue } from "../api/pipelines";
import { NodeRunBadge } from "../runs/NodeRunBadge";
import type { NodeRunState } from "../runs/runState";

export type OperationNodeData = {
  nodeId: string;
  operationId: string;
  operation: OperationDescriptor | undefined;
  enabled: boolean;
  issues: ValidationIssue[];
  /** Present only while a submitted run that contains this node is shown. */
  run?: { state: NodeRunState | undefined };
};

export type OperationFlowNode = Node<OperationNodeData, "operation">;

function PortRow({ port, side, issues }: { port: PortDescriptor; side: "in" | "out"; issues: ValidationIssue[] }) {
  const invalid = issues.some((issue) => issue.port === port.name);
  return (
    <li className={`op-node__port op-node__port--${side}`} data-invalid={invalid || undefined}>
      <Handle
        type={side === "in" ? "target" : "source"}
        position={side === "in" ? Position.Left : Position.Right}
        id={port.name}
        className="op-node__handle"
        title={`${port.name}: ${port.type.kind}${port.cardinality === "many" ? ", many" : ""}`}
      />
      <span className="op-node__port-name">{port.name}</span>
      <span className="op-node__port-kind">{port.type.kind}</span>
    </li>
  );
}

/** One catalogue operation on the canvas, with a typed handle per port. */
export function OperationNode({ data, selected }: NodeProps<OperationFlowNode>) {
  const { operation, issues } = data;
  return (
    <div
      className="op-node"
      data-selected={selected || undefined}
      data-bypassed={!data.enabled || undefined}
      data-invalid={issues.length > 0 || undefined}
      data-run-status={data.run ? (data.run.state?.status ?? "not-started") : undefined}
    >
      <div className="op-node__header">
        <span className="op-node__title">{operation?.title ?? "Unknown operation"}</span>
        <code className="op-node__id">{data.nodeId}</code>
      </div>
      <code className="op-node__operation">{data.operationId}</code>
      {data.run && <NodeRunBadge state={data.run.state} />}
      {!data.enabled && <p className="op-node__badge">Bypassed</p>}
      {operation && !operation.available && <p className="op-node__badge op-node__badge--warn">Unavailable</p>}
      {operation && (
        <div className="op-node__ports">
          <ul aria-label="Inputs">
            {operation.inputs.map((port) => (
              <PortRow key={port.name} port={port} side="in" issues={issues} />
            ))}
          </ul>
          <ul aria-label="Outputs">
            {operation.outputs.map((port) => (
              <PortRow key={port.name} port={port} side="out" issues={issues} />
            ))}
          </ul>
        </div>
      )}
      {issues.length > 0 && (
        <ul className="op-node__issues">
          {issues.map((issue, index) => (
            <li key={index}>{issue.port ? `${issue.port}: ${issue.message}` : issue.message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
