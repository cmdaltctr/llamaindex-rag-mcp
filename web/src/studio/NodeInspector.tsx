import type { EffectiveControl, OperationDescriptor, ValidationIssue } from "../api/pipelines";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { findOperation } from "./connections";
import { removeNode, setEnabled, setParam, toggleGraphInput, toggleGraphOutput, type Draft } from "./graph";
import { ParamField } from "./ParamField";
import { paramFields } from "./schema";

interface NodeInspectorProps {
  draft: Draft;
  nodeId: string | null;
  catalogue: readonly OperationDescriptor[];
  issues: readonly ValidationIssue[];
  controls: Record<string, EffectiveControl[]>;
  onChange: (change: (draft: Draft) => Draft) => void;
}

const PANEL = "flex flex-col gap-3 rounded-panel border border-border bg-card p-4";

function Check({ checked, onChange, children }: { checked: boolean; onChange: (checked: boolean) => void; children: string }) {
  return (
    <label className="flex items-center gap-2 text-ui">
      <input type="checkbox" checked={checked} className="size-4 accent-primary" onChange={(event) => onChange(event.target.checked)} />
      {children}
    </label>
  );
}

/** Settings for the selected node, generated from its operation's catalogue entry. */
export function NodeInspector({ draft, nodeId, catalogue, issues, controls, onChange }: NodeInspectorProps) {
  const node = draft.graph.nodes.find((candidate) => candidate.id === nodeId);
  if (!node) {
    return (
      <section aria-label="Node settings" className={PANEL}>
        <h2 className="text-section-title font-semibold">Node settings</h2>
        <p className="text-meta text-muted-foreground">Select a node to edit its settings.</p>
      </section>
    );
  }
  const id = node.id;
  const operation = findOperation(catalogue, node.operation, node.version);
  const nodeIssues = issues.filter((issue) => issue.node_id === id);
  const isInput = (port: string) => draft.graph.inputs.some((i) => i.targets.some((t) => t.node === id && t.port === port));
  const isOutput = (port: string) => draft.graph.outputs.some((o) => o.source.node === id && o.source.port === port);

  return (
    <section aria-label="Node settings" className={PANEL}>
      <h2 className="text-section-title font-semibold">
        Node <code className="font-mono">{id}</code>
      </h2>
      <p className="flex flex-wrap items-center gap-1.5 text-meta text-muted-foreground">
        {operation?.title ?? "Unknown operation"}
        {operation && <Badge variant="hue">{operation.family}</Badge>}
        <code className="font-mono text-code">{node.operation}</code>
      </p>
      {operation?.description && <p className="text-meta text-muted-foreground">{operation.description}</p>}
      {operation && !operation.available && (
        <p className="text-meta text-status-warning-label">Unavailable on this host: {operation.unavailable_reasons.join(" ")}</p>
      )}
      {nodeIssues.length > 0 && (
        <ul className="flex flex-col gap-1">
          {nodeIssues.map((issue, index) => (
            <li key={index} className="text-meta text-status-error-label">
              <code className="font-mono text-code">{issue.code}</code> {issue.port ? `${issue.port}: ` : ""}
              {issue.message}
            </li>
          ))}
        </ul>
      )}
      {operation?.bypass && (
        <>
          <Check checked={node.enabled === false} onChange={(checked) => onChange((current) => setEnabled(current, id, !checked))}>
            Bypass this node
          </Check>
          <p className="text-meta text-muted-foreground">
            A bypassed node passes its <code className="font-mono text-code">{operation.bypass.input_port}</code> input through unchanged.
          </p>
        </>
      )}
      {operation &&
        paramFields(operation).map((field) => (
          <ParamField
            key={`${id}:${field.name}`}
            field={field}
            value={node.params?.[field.name]}
            effective={field.lever ? controls[id]?.find((control) => control.lever === field.lever) : undefined}
            onChange={(value) => onChange((current) => setParam(current, id, field.name, value))}
          />
        ))}
      {operation && (operation.inputs.length > 0 || operation.outputs.length > 0) && (
        <fieldset className="flex min-w-0 flex-col gap-2 rounded-control border border-border p-3">
          <legend className="px-1 text-ui font-medium">Graph inputs and outputs</legend>
          {operation.inputs.map((port) => (
            <Check
              key={`in:${port.name}`}
              checked={isInput(port.name)}
              onChange={(checked) => onChange((current) => toggleGraphInput(current, id, port.name, port.type.kind, checked))}
            >
              {`Use input ${port.name} as a graph input`}
            </Check>
          ))}
          {operation.outputs.map((port) => (
            <Check
              key={`out:${port.name}`}
              checked={isOutput(port.name)}
              onChange={(checked) => onChange((current) => toggleGraphOutput(current, id, port.name, checked))}
            >
              {`Expose output ${port.name} as a graph output`}
            </Check>
          ))}
        </fieldset>
      )}
      <Button variant="destructive" onClick={() => onChange((current) => removeNode(current, id))}>
        Remove node
      </Button>
    </section>
  );
}
