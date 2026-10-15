import { Search } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import type { JsonObject, QueryControls } from "../api/documents";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";

interface SearchFormProps {
  collection: string;
  busy: boolean;
  onSubmit: (controls: QueryControls) => void;
}

/** Parses the optional controls. Empty fields become `null`, so the profile decides them. */
function readControls(query: string, topK: string, filter: string): QueryControls | string {
  if (query.trim() === "") return "Enter a query.";
  let top_k: number | null = null;
  if (topK.trim() !== "") {
    top_k = Number(topK);
    if (!Number.isInteger(top_k) || top_k < 1) return "Results must be a whole number of 1 or more.";
  }
  let metadata_filter: JsonObject | null = null;
  if (filter.trim() !== "") {
    let parsed: unknown;
    try {
      parsed = JSON.parse(filter);
    } catch {
      return "The metadata filter must be a JSON object.";
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return "The metadata filter must be a JSON object.";
    metadata_filter = parsed as JsonObject;
  }
  return { query, top_k, metadata_filter };
}

const TRI_STATE = { inherit: null, on: true, off: false } as const;
type TriKey = keyof typeof TRI_STATE;

/** Inherit, on or off. Inherit sends `null`, so the collection profile decides. */
function TriStateSelect({ label, value, onChange }: { label: string; value: boolean | null; onChange: (value: boolean | null) => void }) {
  const id = useId();
  const current: TriKey = value === null ? "inherit" : value ? "on" : "off";
  return (
    <div className="flex w-40 max-w-full flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select value={current} onValueChange={(key) => onChange(TRI_STATE[key as TriKey])}>
        <SelectTrigger id={id}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="inherit">Profile decides</SelectItem>
          <SelectItem value="on">On</SelectItem>
          <SelectItem value="off">Off</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}

export function SearchForm({ collection, busy, onSubmit }: SearchFormProps) {
  const id = useId();
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState("");
  const [filter, setFilter] = useState("");
  const [rerank, setRerank] = useState<boolean | null>(null);
  const [hybrid, setHybrid] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const controls = readControls(query, topK, filter);
    if (typeof controls === "string") {
      setError(controls);
      return;
    }
    setError(null);
    onSubmit({ ...controls, rerank, hybrid });
  }

  return (
    <form role="search" aria-label={`Search ${collection}`} onSubmit={submit} className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${id}-q`}>Query</Label>
        <Input id={`${id}-q`} type="search" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex w-40 max-w-full flex-col gap-1.5">
          <Label htmlFor={`${id}-k`}>Results (top_k)</Label>
          <Input
            id={`${id}-k`}
            type="number"
            min={1}
            inputMode="numeric"
            placeholder="Profile decides"
            value={topK}
            onChange={(e) => setTopK(e.target.value)}
          />
        </div>
        <TriStateSelect label="Rerank" value={rerank} onChange={setRerank} />
        <TriStateSelect label="Hybrid" value={hybrid} onChange={setHybrid} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${id}-f`}>Metadata filter (JSON)</Label>
        <Input
          id={`${id}-f`}
          dir="ltr"
          className="font-mono text-code"
          aria-describedby={`${id}-hint`}
          placeholder='{"file_type": "md"}'
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <p id={`${id}-hint`} className="text-meta text-muted-foreground">
          Empty controls use the collection profile.
        </p>
      </div>
      {error !== null ? (
        <p role="alert" className="text-ui text-status-error-label">
          {error}
        </p>
      ) : null}
      <div>
        <Button type="submit" disabled={busy}>
          <Search aria-hidden="true" />
          Run search
        </Button>
      </div>
    </form>
  );
}
