import type { EffectiveControl, OperationDescriptor, ValidationIssue } from "../api/pipelines";
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

/** Settings for the selected node, generated from its operation's catalogue entry. */
export function NodeInspector({ draft, nodeId, catalogue, issues, controls, onChange }: NodeInspectorProps) {
  const node = draft.graph.nodes.find((candidate) => candidate.id === nodeId);
  if (!node) {
    return (
      <section className="canvas-panel" aria-label="Node settings">
        <h2 className="type-section-title">Node settings</h2>
        <p className="type-meta">Select a node to edit its settings.</p>
      </section>
    );
  }
  const id = node.id;
  const operation = findOperation(catalogue, node.operation, node.version);
  const nodeIssues = issues.filter((issue) => issue.node_id === id);
  const isInput = (port: string) => draft.graph.inputs.some((i) => i.targets.some((t) => t.node === id && t.port === port));
  const isOutput = (port: string) => draft.graph.outputs.some((o) => o.source.node === id && o.source.port === port);

  return (
    <section className="canvas-panel inspector-panel" aria-label="Node settings">
      <h2 className="type-section-title">
        Node <code>{id}</code>
      </h2>
      <p className="type-meta">
        {operation?.title ?? "Unknown operation"} <code>{node.operation}</code>
      </p>
      {operation?.description && <p className="type-meta">{operation.description}</p>}
      {operation && !operation.available && (
        <p className="canvas-warning type-meta">Unavailable on this host: {operation.unavailable_reasons.join(" ")}</p>
      )}
      {nodeIssues.length > 0 && (
        <ul className="issue-list">
          {nodeIssues.map((issue, index) => (
            <li key={index} className="canvas-error type-meta">
              <code>{issue.code}</code> {issue.port ? `${issue.port}: ` : ""}
              {issue.message}
            </li>
          ))}
        </ul>
      )}
      {operation?.bypass && (
        <label className="param__choice">
          <input
            type="checkbox"
            checked={node.enabled === false}
            onChange={(event) => onChange((current) => setEnabled(current, id, !event.target.checked))}
          />
          Bypass this node
        </label>
      )}
      {operation?.bypass && (
        <p className="type-meta">
          A bypassed node passes its <code>{operation.bypass.input_port}</code> input through unchanged.
        </p>
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
        <fieldset className="param">
          <legend className="param__legend">Graph inputs and outputs</legend>
          {operation.inputs.map((port) => (
            <label key={`in:${port.name}`} className="param__choice">
              <input
                type="checkbox"
                checked={isInput(port.name)}
                onChange={(event) =>
                  onChange((current) => toggleGraphInput(current, id, port.name, port.type.kind, event.target.checked))
                }
              />
              {`Use input ${port.name} as a graph input`}
            </label>
          ))}
          {operation.outputs.map((port) => (
            <label key={`out:${port.name}`} className="param__choice">
              <input
                type="checkbox"
                checked={isOutput(port.name)}
                onChange={(event) => onChange((current) => toggleGraphOutput(current, id, port.name, event.target.checked))}
              />
              {`Expose output ${port.name} as a graph output`}
            </label>
          ))}
        </fieldset>
      )}
      <button type="button" className="button button--ghost" onClick={() => onChange((current) => removeNode(current, id))}>
        Remove node
      </button>
    </section>
  );
}
