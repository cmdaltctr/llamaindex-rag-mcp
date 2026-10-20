import type { ReactNode } from "react";
import type { EffectiveControl, OperationDescriptor } from "../api/pipelines";
import { setEnabled, setParam, type Draft } from "./graph";
import { ParamField } from "./ParamField";
import { paramFields } from "./schema";
import { controlFor, valueNote } from "./stepSummary";

interface StepSettingsFieldsProps {
  draft: Draft;
  nodeId: string;
  operation: OperationDescriptor;
  /** Effective control values from the latest check, keyed by node id. */
  controls: Record<string, EffectiveControl[]>;
  onChange: (change: (draft: Draft) => Draft) => void;
  readOnly?: boolean;
  /** Shown between the bypass switch and the parameters, for example the embedding model. */
  children?: ReactNode;
}

export function Check({ checked, onChange, disabled, children }: { checked: boolean; onChange: (checked: boolean) => void; disabled: boolean; children: string }) {
  return (
    <label className="flex items-center gap-2 text-ui">
      <input type="checkbox" checked={checked} disabled={disabled} className="size-4 accent-primary" onChange={(event) => onChange(event.target.checked)} />
      {children}
    </label>
  );
}

/**
 * The editable settings of one step: the bypass switch when the operation has
 * one, and one control for each parameter. Step settings and the card settings
 * panel both render it, so a control behaves the same in both places.
 */
export function StepSettingsFields({ draft, nodeId, operation, controls, onChange, readOnly = false, children }: StepSettingsFieldsProps) {
  const node = draft.graph.nodes.find((candidate) => candidate.id === nodeId);
  if (!node) return null;
  return (
    <>
      {operation.bypass && (
        <>
          <Check disabled={readOnly} checked={node.enabled === false} onChange={(checked) => onChange((current) => setEnabled(current, nodeId, !checked))}>
            Bypass this step
          </Check>
          <p className="text-meta text-muted-foreground">
            A bypassed node passes its <code className="font-mono text-code">{operation.bypass.input_port}</code> input through unchanged.
          </p>
        </>
      )}
      {children}
      {paramFields(operation).map((field) => (
        <ParamField
          key={`${nodeId}:${field.name}`}
          field={field}
          disabled={readOnly}
          value={node.params?.[field.name]}
          note={valueNote(field, node, controlFor(field, controls[nodeId]), draft.graph)}
          onChange={(value) => onChange((current) => setParam(current, nodeId, field.name, value))}
        />
      ))}
    </>
  );
}
