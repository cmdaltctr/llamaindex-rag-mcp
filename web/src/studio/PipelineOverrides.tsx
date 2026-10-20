import { useId } from "react";
import type { JsonValue } from "../api/pipelines";
import { Button } from "../components/ui/button";
import { withGraph, type Draft } from "./graph";
import { mappedFieldLabel } from "./labels";
import { ParamField } from "./ParamField";
import type { ParamField as Field } from "./schema";

/** The one allowed lever that no step parameter carries, so Pipeline settings offers it (design D4). */
export const RERANK_FACTOR = "retrieval.rerank_fetch_multiplier";

const RERANK_FACTOR_FIELD: Field = {
  name: "rerank_fetch_multiplier",
  title: "Rerank fetch multiplier",
  label: mappedFieldLabel({ name: RERANK_FACTOR, title: RERANK_FACTOR, lever: RERANK_FACTOR }) ?? "Rerank candidate factor",
  description: "How many candidates the reranker reads, as a multiple of the number of results.",
  kind: "integer",
  nullable: true,
  options: [],
  minimum: 1,
  defaultValue: null,
  lever: RERANK_FACTOR,
  unavailableOptions: {},
  inheritedValue: undefined,
  isCollection: false,
};

interface PipelineOverridesProps {
  draft: Draft;
  onChange: (change: (draft: Draft) => Draft) => void;
  /** Search and Answer offer the rerank candidate factor. */
  rerankFactor: boolean;
  readOnly?: boolean;
}

const labelOf = (lever: string) => mappedFieldLabel({ name: lever, title: lever, lever }) ?? lever;

function formatOverride(value: JsonValue): string {
  if (typeof value === "boolean") return value ? "On" : "Off";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}

function setOverride(draft: Draft, lever: string, value: JsonValue | undefined): Draft {
  const overrides = { ...draft.graph.overrides };
  if (value === null || value === undefined) delete overrides[lever];
  else overrides[lever] = value;
  return withGraph(draft, { overrides });
}

/**
 * The pipeline-wide overrides that the graph holds, each with Remove, and the
 * rerank candidate factor on Search and Answer. The lever paths show only in
 * the Details area.
 */
export function PipelineOverrides({ draft, onChange, rerankFactor, readOnly = false }: PipelineOverridesProps) {
  const entries = Object.entries(draft.graph.overrides).filter(([lever]) => !(rerankFactor && lever === RERANK_FACTOR));
  const factor = draft.graph.overrides[RERANK_FACTOR];
  const headingId = useId();
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <h3 id={headingId} className="text-ui font-medium">
          Pipeline-wide settings
        </h3>
        {entries.length === 0 ? (
          <p className="text-meta text-muted-foreground">No pipeline-wide settings.</p>
        ) : (
          <ul aria-labelledby={headingId} className="flex flex-col gap-1">
            {entries.map(([lever, value]) => (
              <li key={lever} className="flex items-center justify-between gap-2 text-ui">
                <span className="min-w-0 [overflow-wrap:anywhere]">{`${labelOf(lever)}: ${formatOverride(value)}`}</span>
                <Button variant="outline" size="sm" disabled={readOnly} aria-label={`Remove ${labelOf(lever)}`} onClick={() => onChange((d) => setOverride(d, lever, undefined))}>
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {rerankFactor && (
        <ParamField
          field={RERANK_FACTOR_FIELD}
          value={factor}
          disabled={readOnly}
          note={factor == null ? "Inherit uses the value of the profile or the server." : `Value in use: ${formatOverride(factor)} (from pipeline settings)`}
          onChange={(value) => onChange((d) => setOverride(d, RERANK_FACTOR, value))}
        />
      )}
      {(entries.length > 0 || rerankFactor) && (
        <details className="text-meta text-muted-foreground">
          <summary className="cursor-pointer">Details</summary>
          <ul className="mt-1 flex flex-col gap-0.5">
            {[...entries.map(([lever]) => lever), ...(rerankFactor ? [RERANK_FACTOR] : [])].map((lever) => (
              <li key={lever}>
                {`${labelOf(lever)}: `}
                <code className="font-mono text-code">{lever}</code>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
