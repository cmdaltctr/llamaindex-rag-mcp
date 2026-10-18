import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Settings2 } from "lucide-react";
import { useState, type KeyboardEvent, type MouseEvent } from "react";
import type { LayoutDirection, OperationDescriptor, PortDescriptor, ValidationIssue } from "../api/pipelines";
import { Badge } from "../components/ui/badge";
import { cn } from "../lib/utils";
import type { NodeRunState } from "../runs/runState";
import { NodeRunStatus } from "./NodeRunStatus";

export type OperationNodeData = {
  nodeId: string;
  operationId: string;
  operation: OperationDescriptor | undefined;
  /** The plain step name: the catalogue title. */
  title: string;
  /** True when another step has the same name, so the node id tells them apart. */
  showNodeId: boolean;
  /** The first sentence of the catalogue description. */
  summary: string;
  /** Up to three main settings, each with its value text. */
  settings: { label: string; value: string }[];
  /** The other editable settings, shown when the user expands the mini card. */
  extraSettings: { label: string; value: string }[];
  /** The number of extra settings. */
  moreSettings: number;
  /** Ports that have a connection, as `in:<port>` or `out:<port>`. The handle of each shows in the success colour. */
  connected: string[];
  /** Set on Embed chunks only: the host embedding model, or `null` when it is not known. */
  model?: { name: string | null };
  enabled: boolean;
  issues: ValidationIssue[];
  /** Which way the graph runs. Inputs sit left and outputs right when horizontal, top and bottom when vertical. */
  direction?: LayoutDirection;
  /** Present only while a run that contains this node is shown. */
  run?: { state: NodeRunState | undefined };
};

export type OperationFlowNode = Node<OperationNodeData, "operation">;

interface PortRowProps {
  port: PortDescriptor;
  side: "in" | "out";
  issues: ValidationIssue[];
  connectable: boolean;
  connected: boolean;
  direction: LayoutDirection;
}

function PortRow({ port, side, issues, connectable, connected, direction }: PortRowProps) {
  const invalid = issues.some((issue) => issue.port === port.name);
  const vertical = direction === "vertical";
  const position = vertical ? (side === "in" ? Position.Top : Position.Bottom) : side === "in" ? Position.Left : Position.Right;
  return (
    // Vertical: the inputs row is the first thing in the card and the outputs row the last, so the handle
    // (pulled out to the card edge) sits directly above or below its own label.
    <li className={cn("relative flex flex-col py-1", vertical ? "items-center px-2" : side === "in" ? "ps-2" : "items-end pe-2")} data-invalid={invalid || undefined}>
      <Handle
        type={side === "in" ? "target" : "source"}
        position={position}
        style={vertical ? (side === "in" ? { top: "-0.5rem" } : { bottom: "-0.5rem" }) : undefined}
        id={port.name}
        isConnectable={connectable}
        data-connected={connected || undefined}
        className={cn("size-2.5", connected ? "border-status-success bg-status-success" : "border-muted-foreground bg-card")}
        title={port.name}
      />
      <span className={cn(invalid && "font-semibold text-status-error-label")}>{port.name}</span>
    </li>
  );
}

function borderFor(data: OperationNodeData, selected: boolean): string {
  const runStatus = data.run?.state?.status;
  if (data.issues.length > 0 || runStatus === "failed") return "border-status-error";
  if (selected) return "border-primary ring-1 ring-primary";
  if (runStatus === "running") return "border-status-info ring-1 ring-status-info";
  return "border-border-hover transition-colors duration-150 hover:border-muted-foreground";
}

/**
 * The one-line summary. A click shows the whole sentence on the card and a second
 * click folds it. It is a button, so the keyboard reaches it, and it stops the
 * click and key events so that using it does not select or drag the card.
 */
function Summary({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const stop = (event: MouseEvent | KeyboardEvent) => event.stopPropagation();
  return (
    <button
      type="button"
      aria-expanded={expanded}
      className={cn("nodrag nopan cursor-pointer text-start text-code text-muted-foreground hover:text-foreground", !expanded && "line-clamp-1")}
      onClick={(event) => {
        stop(event);
        setExpanded((current) => !current);
      }}
      onKeyDown={stop}
    >
      {text}
    </button>
  );
}

/**
 * The settings of the step in a mini card nested in the card, so they read as
 * one group: the main settings, the Embed chunks model line or "No settings".
 * A button shows the other settings in place. It stops the click and key events
 * so that using it does not select or drag the card.
 */
function SettingsCard({ data, hasSettings }: { data: OperationNodeData; hasSettings: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const stop = (event: MouseEvent | KeyboardEvent) => event.stopPropagation();
  const shown = expanded ? [...data.settings, ...data.extraSettings] : data.settings;
  return (
    <div data-slot="node-settings" role="group" aria-label="Settings" className="flex flex-col gap-1 rounded-small border border-border bg-secondary p-2">
      {shown.length > 0 && (
        <ul>
          {shown.map((setting) => (
            <li key={setting.label}>
              {setting.label}: <span className="text-muted-foreground">{setting.value}</span>
            </li>
          ))}
        </ul>
      )}
      {data.moreSettings > 0 && (
        <button
          type="button"
          aria-expanded={expanded}
          className="nodrag nopan cursor-pointer self-start text-start text-muted-foreground hover:text-foreground"
          onClick={(event) => {
            stop(event);
            setExpanded((current) => !current);
          }}
          onKeyDown={stop}
        >
          {expanded ? "Show fewer settings" : `+${data.moreSettings} more settings`}
        </button>
      )}
      {data.model && (
        <p>
          Model: {data.model.name ? <code className="font-mono text-code">{data.model.name}</code> : "unknown"}{" "}
          <span className="text-muted-foreground">(fixed for collections that already hold vectors)</span>
        </p>
      )}
      {!hasSettings && !data.model && <p className="text-muted-foreground">No settings</p>}
    </div>
  );
}

/** One catalogue operation on the canvas: what the step does, its main settings, and a typed handle per port. */
export function OperationNode({ data, selected, isConnectable }: NodeProps<OperationFlowNode>) {
  const { operation, issues } = data;
  const hasSettings = data.settings.length > 0 || data.moreSettings > 0;
  const direction = data.direction ?? "horizontal";
  const vertical = direction === "vertical";
  const portRows = (side: "in" | "out") =>
    (side === "in" ? operation?.inputs : operation?.outputs)?.map((port) => (
      <PortRow key={port.name} port={port} side={side} issues={issues} connectable={isConnectable} connected={data.connected.includes(`${side}:${port.name}`)} direction={direction} />
    ));
  const inputs = (
    <ul aria-label="Inputs" className={cn(vertical && "flex justify-around")}>
      {portRows("in")}
    </ul>
  );
  const outputs = (
    <ul aria-label="Outputs" className={cn(vertical && "flex justify-around")}>
      {portRows("out")}
    </ul>
  );
  return (
    <div
      data-slot="op-node"
      data-selected={selected || undefined}
      data-bypassed={!data.enabled || undefined}
      data-invalid={issues.length > 0 || undefined}
      data-run-status={data.run ? (data.run.state?.status ?? "not-started") : undefined}
      className={cn(
        "relative flex min-w-52 max-w-60 flex-col gap-1 rounded-control border bg-card p-2 text-meta text-card-foreground",
        borderFor(data, Boolean(selected)),
        !data.enabled && "border-dashed opacity-80",
      )}
    >
      {operation && vertical && inputs}
      <div className="flex items-start justify-between gap-2">
        <span className="font-semibold">{data.title}</span>
        <Settings2 aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {operation && <Badge variant="hue">{operation.family}</Badge>}
        {data.showNodeId && <code className="font-mono text-code text-muted-foreground [overflow-wrap:anywhere]">{data.nodeId}</code>}
      </div>
      {data.summary && <Summary text={data.summary} />}
      <SettingsCard data={data} hasSettings={hasSettings} />
      {data.run && <NodeRunStatus state={data.run.state} />}
      {!data.enabled && <Badge variant="neutral">Bypassed</Badge>}
      {operation && !operation.available && <Badge variant="warning">Unavailable</Badge>}
      {operation && !vertical && <div className="grid grid-cols-2 gap-2">{inputs}{outputs}</div>}
      {operation && vertical && outputs}
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
