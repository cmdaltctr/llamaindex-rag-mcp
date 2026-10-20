import { useId } from "react";
import type { OperationDescriptor } from "../api/pipelines";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import type { Purpose } from "../lib/routes";
import { setCollection, type Draft } from "./graph";
import { disableHybrid, enableHybrid, hybridState } from "./hybrid";
import { PipelineOverrides } from "./PipelineOverrides";

interface PipelineBarProps {
  draft: Draft;
  onChange: (change: (draft: Draft) => Draft) => void;
  /** Search and Answer show the hybrid switch and the rerank candidate factor. */
  purpose: Purpose;
  catalogue: readonly OperationDescriptor[];
  /** A read-only graph shows its settings without allowing a change. */
  readOnly?: boolean;
}

export const HYBRID_LINE = "Adds keyword (sparse) search and merges it with vector search.";
export const HYBRID_READ_ONLY = "Duplicate this profile to turn hybrid retrieval on or off.";
export const HYBRID_CUSTOM = "This pipeline has a custom retrieval shape. Change it with the steps on the canvas.";

function HybridSwitch({ draft, onChange, catalogue, readOnly, purpose }: Required<PipelineBarProps>) {
  const lineId = useId();
  const state = hybridState(draft, catalogue);
  const on = state.kind === "on" || ((state.kind === "custom" || state.kind === "unavailable") && state.on);
  const reason = readOnly ? HYBRID_READ_ONLY : state.kind === "custom" ? HYBRID_CUSTOM : state.kind === "unavailable" ? state.reason : null;
  const toggle = () => onChange((d) => (hybridState(d, catalogue).kind === "on" ? disableHybrid(d) : enableHybrid(d, catalogue)));
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-ui font-medium">Hybrid retrieval</span>
        <Button variant="outline" size="sm" role="switch" aria-checked={on} aria-label="Hybrid retrieval" aria-describedby={lineId} disabled={reason !== null} onClick={toggle}>
          {on ? "On" : "Off"}
        </Button>
      </div>
      <div id={lineId} className="text-meta text-muted-foreground">
        <p>{HYBRID_LINE}</p>
        <p>{`Changes the ${purpose === "answer" ? "Answer" : "Search"} pipeline only.`}</p>
      </div>
      {reason !== null && <p className="text-meta text-status-warning-label">{reason}</p>}
    </div>
  );
}

/** Base profile (read-only), default collection, hybrid switch and pipeline-wide settings of the open pipeline. */
export function PipelineBar({ draft, onChange, purpose, catalogue, readOnly = false }: PipelineBarProps) {
  const idBase = useId();
  const retrieval = purpose === "search" || purpose === "answer";
  return (
    <div className="flex flex-col gap-3">
      <p className="text-ui text-muted-foreground">{`Base profile: ${draft.graph.profile ?? "inherited from each collection"}`}</p>
      <div className="flex min-w-0 flex-col gap-1.5">
        <Label htmlFor={`${idBase}-collection`}>Collection</Label>
        <Input
          id={`${idBase}-collection`}
          disabled={readOnly}
          value={draft.graph.collection ?? ""}
          placeholder="Host default"
          onChange={(event) => onChange((d) => setCollection(d, event.target.value))}
        />
      </div>
      {retrieval && <HybridSwitch draft={draft} onChange={onChange} catalogue={catalogue} readOnly={readOnly} purpose={purpose} />}
      <PipelineOverrides draft={draft} onChange={onChange} rerankFactor={retrieval} readOnly={readOnly} />
    </div>
  );
}
