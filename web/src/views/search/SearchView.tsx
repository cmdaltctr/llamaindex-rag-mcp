import { useState } from "react";
import type { FetchLike } from "../../api/client";
import { listCollections, listDocuments, searchCollection, type DocumentInfo, type QueryControls, type SearchHit } from "../../api/documents";
import { ChunkViewer } from "../shared/ChunkViewer";
import { ErrorNotice, ViewHeader } from "../shared/controls";
import { messageOf } from "../shared/labels";
import { useLoad } from "../shared/useLoad";
import "../views.css";
import { ResultList } from "./ResultList";
import { SearchForm } from "./SearchForm";

interface SearchViewProps {
  fetchImpl?: FetchLike;
  focusHeading?: boolean;
}

interface Outcome {
  collection: string;
  hits: SearchHit[];
  /** `null` when the source listing failed: availability is then unknown. */
  sources: DocumentInfo[] | null;
}

/** Search one collection through the shared core path; omitted controls stay with the profile. */
export function SearchView({ fetchImpl, focusHeading = false }: SearchViewProps) {
  const collections = useLoad(() => listCollections({ fetchImpl }), "collections");
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [chunkId, setChunkId] = useState<string | null>(null);
  const active = collections.data?.find((c) => c.name === selected)?.name ?? collections.data?.[0]?.name ?? null;

  async function run(controls: QueryControls) {
    if (active === null) return;
    setBusy(true);
    setError(null);
    setChunkId(null);
    try {
      const [hits, sources] = await Promise.all([
        searchCollection(active, controls, { fetchImpl }),
        listDocuments(active, { fetchImpl }).catch(() => null),
      ]);
      setOutcome({ collection: active, hits, sources });
    } catch (problem) {
      setOutcome(null);
      setError(messageOf(problem));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="view view--documents" aria-labelledby="view-search-title">
      <ViewHeader id="search" focusHeading={focusHeading} />
      <ErrorNotice message={collections.error} />
      <SearchForm collections={collections.data} collection={active} busy={busy} onCollection={setSelected} onSubmit={(c) => void run(c)} />
      <ErrorNotice message={error} />
      {outcome === null || outcome.hits.length === 0 ? (
        <div className="empty-state" data-testid="empty-state">
          <p className="empty-state__title">{outcome === null ? "No search yet" : "No results"}</p>
          <p className="text-meta">
            {outcome === null ? "Results appear here with their score kind and source." : "Try another query or fewer filters."}
          </p>
        </div>
      ) : (
        <ResultList hits={outcome.hits} sources={outcome.sources} onShowChunk={setChunkId} />
      )}
      {outcome !== null && chunkId !== null ? (
        <ChunkViewer collection={outcome.collection} chunkId={chunkId} fetchImpl={fetchImpl} onClose={() => setChunkId(null)} />
      ) : null}
    </section>
  );
}
