import { useQuery } from "@tanstack/react-query";
import { SearchCheck, SearchX } from "lucide-react";
import { useState } from "react";
import { useApi } from "../api/ApiProvider";
import { useSearch } from "../api/mutations";
import { documentsQuery } from "../api/queries";
import { ChunkViewer } from "../components/ChunkViewer";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/ErrorNotice";
import { ResultList } from "./ResultList";
import { SearchForm } from "./SearchForm";

/** Search the open project through the shared core path; omitted controls stay with the profile. */
export function SearchSection({ collection }: { collection: string }) {
  const search = useSearch(collection);
  const sources = useQuery(documentsQuery(useApi(), collection));
  const [chunkId, setChunkId] = useState<string | null>(null);

  return (
    <section aria-labelledby="kb-search-title" className="flex flex-col gap-4">
      <h2 id="kb-search-title" className="text-section-title font-semibold">
        Search {collection}
      </h2>
      <SearchForm collection={collection} busy={search.isPending} onSubmit={(controls) => search.mutate(controls)} />
      {search.isError ? <ErrorNotice error={search.error} onRetry={() => search.variables && search.mutate(search.variables)} /> : null}
      {search.isPending ? (
        <p role="status" className="text-meta text-muted-foreground">
          Searching.
        </p>
      ) : null}
      {search.isIdle ? <EmptyState icon={SearchCheck} message="No search yet. Results appear here with their score kind and source." /> : null}
      {search.isSuccess && search.data.length === 0 ? <EmptyState icon={SearchX} message="No results. Try another query or fewer filters." /> : null}
      {search.isSuccess && search.data.length > 0 ? <ResultList hits={search.data} sources={sources.data} onShowChunk={setChunkId} /> : null}
      {chunkId !== null ? <ChunkViewer key={chunkId} collection={collection} chunkId={chunkId} onClose={() => setChunkId(null)} /> : null}
    </section>
  );
}
