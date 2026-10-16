import { useId } from "react";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { setCollection, setProfile, setTitle, type Draft } from "./graph";

interface PipelineBarProps {
  draft: Draft;
  onChange: (change: (draft: Draft) => Draft) => void;
}

const INHERIT = "__inherit__";

/** Title, operational profile and default collection of the open pipeline. */
export function PipelineBar({ draft, onChange }: PipelineBarProps) {
  const idBase = useId();
  return (
    <div className="flex flex-col gap-3">
      <div className="flex min-w-0 flex-col gap-1.5">
        <Label htmlFor={`${idBase}-title`}>Title</Label>
        <Input id={`${idBase}-title`} value={draft.layout.title} onChange={(event) => onChange((d) => setTitle(d, event.target.value))} />
      </div>
      <div className="flex min-w-0 flex-col gap-1.5">
        <Label htmlFor={`${idBase}-profile`}>Profile</Label>
        <Select value={draft.graph.profile ?? INHERIT} onValueChange={(value) => onChange((d) => setProfile(d, value === INHERIT ? null : value))}>
          <SelectTrigger id={`${idBase}-profile`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={INHERIT}>Inherit from each collection</SelectItem>
            <SelectItem value="documents">documents</SelectItem>
            <SelectItem value="codebase">codebase</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="flex min-w-0 flex-col gap-1.5">
        <Label htmlFor={`${idBase}-collection`}>Collection</Label>
        <Input
          id={`${idBase}-collection`}
          value={draft.graph.collection ?? ""}
          placeholder="Host default"
          onChange={(event) => onChange((d) => setCollection(d, event.target.value))}
        />
      </div>
    </div>
  );
}
