import type { ReactNode } from "react";
import type { EffectiveControl, NodeSpec, OperationDescriptor, ValidationIssue } from "../api/pipelines";
import { paramFields } from "./schema";

interface NodeDetailsProps {
  node: NodeSpec;
  operation: OperationDescriptor | undefined;
  issues: readonly ValidationIssue[];
  controls: readonly EffectiveControl[];
}

const CODE = "font-mono text-code [overflow-wrap:anywhere]";

function Row({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-meta font-medium">{term}</dt>
      <dd className="text-meta text-muted-foreground">{children}</dd>
    </div>
  );
}

function Items({ items }: { items: ReactNode[] }) {
  return (
    <ul className="flex flex-col gap-0.5">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
}

/**
 * The technical identifiers of one step, in a native disclosure that starts
 * closed. Advanced users read ids, setting paths, port types and issue codes here.
 */
export function NodeDetails({ node, operation, issues, controls }: NodeDetailsProps) {
  const fields = operation ? paramFields(operation) : [];
  return (
    <details className="rounded-control border border-border p-3">
      <summary className="cursor-pointer text-ui font-medium">Details</summary>
      <dl className="mt-2 flex flex-col gap-2">
        <Row term="Node ID">
          <code className={CODE}>{node.id}</code>
        </Row>
        <Row term="Operation">
          <code className={CODE}>{node.operation}</code>, version {operation?.version ?? node.version ?? "unknown"}
        </Row>
        {operation?.description && <Row term="Description">{operation.description}</Row>}
        {fields.length > 0 && (
          <Row term="Settings">
            <Items
              items={fields.map((field) => (
                <>
                  {field.label}: <code className={CODE}>{field.lever ?? field.name}</code>
                </>
              ))}
            />
          </Row>
        )}
        {operation && (
          <Row term="Ports">
            <Items
              items={[
                ...operation.inputs.map((port) => (
                  <>
                    Input <code className={CODE}>{port.name}</code>: {port.type.kind}, {port.cardinality}
                  </>
                )),
                ...operation.outputs.map((port) => (
                  <>
                    Output <code className={CODE}>{port.name}</code>: {port.type.kind}, {port.cardinality}
                  </>
                )),
              ]}
            />
          </Row>
        )}
        {issues.length > 0 && (
          <Row term="Issue codes">
            <Items items={issues.map((issue) => <code className={CODE}>{issue.code}</code>)} />
          </Row>
        )}
        {controls.length > 0 && (
          <Row term="Control details">
            <Items
              items={controls.map((control) => (
                <>
                  <code className={CODE}>{control.lever}</code>: {control.detail}
                </>
              ))}
            />
          </Row>
        )}
      </dl>
    </details>
  );
}
