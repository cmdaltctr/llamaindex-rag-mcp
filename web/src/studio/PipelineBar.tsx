import { useId } from "react";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { setCollection, type Draft } from "./graph";

interface PipelineBarProps {
  draft: Draft;
  onChange: (change: (draft: Draft) => Draft) => void;
  /** A read-only graph shows its settings without allowing a change. */
  readOnly?: boolean;
}

/** Base profile (read-only) and default collection of the open pipeline. */
export function PipelineBar({ draft, onChange, readOnly = false }: PipelineBarProps) {
  const idBase = useId();
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
    </div>
  );
}
