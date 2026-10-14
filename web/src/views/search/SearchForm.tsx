import { useId, useState, type FormEvent } from "react";
import type { CollectionInfo, JsonObject, QueryControls } from "../../api/documents";
import { CollectionSelect, ErrorNotice, TriStateSelect } from "../shared/controls";

interface SearchFormProps {
  collections: CollectionInfo[] | undefined;
  collection: string | null;
  busy: boolean;
  onCollection: (name: string) => void;
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

export function SearchForm({ collections, collection, busy, onCollection, onSubmit }: SearchFormProps) {
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
    <form className="panel" role="search" aria-label="Search a collection" onSubmit={submit}>
      <div className="form-row">
        <CollectionSelect collections={collections} value={collection} onChange={onCollection} />
        <div className="field field--grow">
          <label className="field__label" htmlFor={`${id}-q`}>
            Query
          </label>
          <input id={`${id}-q`} className="control" type="search" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
      </div>
      <div className="form-row">
        <div className="field">
          <label className="field__label" htmlFor={`${id}-k`}>
            Results (top_k)
          </label>
          <input
            id={`${id}-k`}
            className="control"
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
      <div className="field">
        <label className="field__label" htmlFor={`${id}-f`}>
          Metadata filter (JSON)
        </label>
        <textarea
          id={`${id}-f`}
          className="control type-code"
          dir="ltr"
          rows={2}
          placeholder='{"file_type": "md"}'
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      <p className="field__hint">Empty controls use the collection profile.</p>
      <ErrorNotice message={error} />
      <div className="button-row">
        <button type="submit" className="button button--tinted" disabled={busy || collection === null}>
          Search
        </button>
      </div>
    </form>
  );
}
