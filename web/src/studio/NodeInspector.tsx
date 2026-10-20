import type { EffectiveControl, OperationDescriptor, ValidationIssue } from "../api/pipelines";
import type { ProfileRecord } from "../api/profiles";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { findOperation } from "./connections";
import { EmbeddingModelSection } from "./EmbeddingModelSection";
import { removeNode, toggleGraphInput, toggleGraphOutput, type Draft } from "./graph";
import { NodeDetails } from "./NodeDetails";
import { firstSentence } from "./stepSummary";
import { Check, StepSettingsFields } from "./StepSettingsFields";

interface NodeInspectorProps {
  draft: Draft;
  nodeId: string | null;
  catalogue: readonly OperationDescriptor[];
  issues: readonly ValidationIssue[];
  controls: Record<string, EffectiveControl[]>;
  onChange: (change: (draft: Draft) => Draft) => void;
  /** A read-only graph shows the values: every field is disabled and the step cannot be removed. */
  readOnly?: boolean;
  /** The open profile. With it, an Embed chunks step shows the profile's embedding model. */
  profile?: ProfileRecord;
}

/** Settings for the selected node, generated from its operation's catalogue entry. */
export function NodeInspector({ draft, nodeId, catalogue, issues, controls, onChange, readOnly = false, profile }: NodeInspectorProps) {
  const node = draft.graph.nodes.find((candidate) => candidate.id === nodeId);
  if (!node) {
    return <p className="text-meta text-muted-foreground">Select a step to edit its settings.</p>;
  }
  const id = node.id;
  const operation = findOperation(catalogue, node.operation, node.version);
  const nodeIssues = issues.filter((issue) => issue.node_id === id);
  const isInput = (port: string) => draft.graph.inputs.some((i) => i.targets.some((t) => t.node === id && t.port === port));
  const isOutput = (port: string) => draft.graph.outputs.some((o) => o.source.node === id && o.source.port === port);
  const embedding = profile !== undefined && node.operation === "embed.chunks" ? <EmbeddingModelSection profile={profile} /> : null;

  return (
    <>
      <h3 className="text-subsection-title font-semibold">{operation?.title ?? "Unknown operation"}</h3>
      {operation && (
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="hue">{operation.family}</Badge>
        </div>
      )}
      {operation?.description && <p className="text-meta text-muted-foreground">{firstSentence(operation.description)}</p>}
      {operation && !operation.available && (
        <p className="text-meta text-status-warning-label">Unavailable on this host: {operation.unavailable_reasons.join(" ")}</p>
      )}
      {nodeIssues.length > 0 && (
        <ul className="flex flex-col gap-1">
          {nodeIssues.map((issue, index) => (
            <li key={index} className="text-meta text-status-error-label">
              {issue.port ? `${issue.port}: ` : ""}
              {issue.message}
            </li>
          ))}
        </ul>
      )}
      {operation ? (
        <StepSettingsFields draft={draft} nodeId={id} operation={operation} controls={controls} onChange={onChange} readOnly={readOnly}>
          {embedding}
        </StepSettingsFields>
      ) : (
        embedding
      )}
      {operation && (operation.inputs.length > 0 || operation.outputs.length > 0) && (
        <fieldset className="flex min-w-0 flex-col gap-2 rounded-control border border-border p-3">
          <legend className="px-1 text-ui font-medium">Graph inputs and outputs</legend>
          {operation.inputs.map((port) => (
            <Check
              key={`in:${port.name}`}
              disabled={readOnly}
              checked={isInput(port.name)}
              onChange={(checked) => onChange((current) => toggleGraphInput(current, id, port.name, port.type.kind, checked))}
            >
              {`Use input ${port.name} as a graph input`}
            </Check>
          ))}
          {operation.outputs.map((port) => (
            <Check
              key={`out:${port.name}`}
              disabled={readOnly}
              checked={isOutput(port.name)}
              onChange={(checked) => onChange((current) => toggleGraphOutput(current, id, port.name, checked))}
            >
              {`Expose output ${port.name} as a graph output`}
            </Check>
          ))}
        </fieldset>
      )}
      {!readOnly && (
        <Button variant="destructive" onClick={() => onChange((current) => removeNode(current, id))}>
          Remove step
        </Button>
      )}
      <NodeDetails node={node} operation={operation} issues={nodeIssues} controls={controls[id] ?? []} />
    </>
  );
}
