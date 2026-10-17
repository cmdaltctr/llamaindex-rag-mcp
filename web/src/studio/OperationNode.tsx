import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import type { OperationDescriptor, PortDescriptor, ValidationIssue } from "../api/pipelines";
import { Badge } from "../components/ui/badge";
import { cn } from "../lib/utils";
import type { NodeRunState } from "../runs/runState";
import { NodeRunStatus } from "./NodeRunStatus";

export type OperationNodeData = {
  nodeId: string;
  operationId: string;
  operation: OperationDescriptor | undefined;
  enabled: boolean;
  issues: ValidationIssue[];
  /** Present only while a run that contains this node is shown. */
  run?: { state: NodeRunState | undefined };
};

export type OperationFlowNode = Node<OperationNodeData, "operation">;

function PortRow({ port, side, issues, connectable }: { port: PortDescriptor; side: "in" | "out"; issues: ValidationIssue[]; connectable: boolean }) {
  const invalid = issues.some((issue) => issue.port === port.name);
  return (
    <li className={cn("relative flex flex-col py-1", side === "in" ? "ps-2" : "items-end pe-2")} data-invalid={invalid || undefined}>
      <Handle
        type={side === "in" ? "target" : "source"}
        position={side === "in" ? Position.Left : Position.Right}
        id={port.name}
        isConnectable={connectable}
        className="size-2.5 border-muted-foreground bg-card"
        title={`${port.name}: ${port.type.kind}${port.cardinality === "many" ? ", many" : ""}`}
      />
      <span className={cn(invalid && "font-semibold text-status-error-label")}>{port.name}</span>
      <span className="font-mono text-code text-muted-foreground">{port.type.kind}</span>
    </li>
  );
}

function borderFor(data: OperationNodeData, selected: boolean): string {
  const runStatus = data.run?.state?.status;
  if (data.issues.length > 0 || runStatus === "failed") return "border-status-error";
  if (selected) return "border-primary ring-1 ring-primary";
  if (runStatus === "running") return "border-status-info ring-1 ring-status-info";
  return "border-border-hover";
}

/** One catalogue operation on the canvas, with a typed handle per port. */
export function OperationNode({ data, selected, isConnectable }: NodeProps<OperationFlowNode>) {
  const { operation, issues } = data;
  return (
    <div
      data-slot="op-node"
      data-selected={selected || undefined}
      data-bypassed={!data.enabled || undefined}
      data-invalid={issues.length > 0 || undefined}
      data-run-status={data.run ? (data.run.state?.status ?? "not-started") : undefined}
      className={cn(
        "flex min-w-52 max-w-68 flex-col gap-1 rounded-control border bg-card p-2 text-meta text-card-foreground",
        borderFor(data, Boolean(selected)),
        !data.enabled && "border-dashed opacity-80",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-semibold">{operation?.title ?? "Unknown operation"}</span>
        <code className="font-mono text-code text-muted-foreground">{data.nodeId}</code>
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {operation && <Badge variant="hue">{operation.family}</Badge>}
        <code className="font-mono text-code text-muted-foreground [overflow-wrap:anywhere]">{data.operationId}</code>
      </div>
      {data.run && <NodeRunStatus state={data.run.state} />}
      {!data.enabled && <Badge variant="neutral">Bypassed</Badge>}
      {operation && !operation.available && <Badge variant="warning">Unavailable</Badge>}
      {operation && (
        <div className="grid grid-cols-2 gap-2">
          <ul aria-label="Inputs">
            {operation.inputs.map((port) => (
              <PortRow key={port.name} port={port} side="in" issues={issues} connectable={isConnectable} />
            ))}
          </ul>
          <ul aria-label="Outputs">
            {operation.outputs.map((port) => (
              <PortRow key={port.name} port={port} side="out" issues={issues} connectable={isConnectable} />
            ))}
          </ul>
        </div>
      )}
      {issues.length > 0 && (
        <ul className="ps-4 text-status-error-label">
          {issues.map((issue, index) => (
            <li key={index}>{issue.port ? `${issue.port}: ${issue.message}` : issue.message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
