import type { DocumentInfo, SearchHit } from "../../api/documents";
import { availabilityLabel, chunkPosition, formatScore, scoreKindLabel } from "../shared/labels";

interface ResultListProps {
  hits: SearchHit[];
  sources: DocumentInfo[] | null;
  onShowChunk: (chunkId: string) => void;
}

/** Machine-local availability for a hit, matched by stable id, else by stored path. */
function availability(hit: SearchHit, sources: DocumentInfo[] | null): boolean | null {
  const match = sources?.find((s) => (hit.source_id !== null ? s.source_id === hit.source_id : s.source_id === null && s.source === hit.source));
  return match?.orphaned ?? null;
}

export function ResultList({ hits, sources, onShowChunk }: ResultListProps) {
  return (
    <ol className="result-list" aria-label="Search results">
      {hits.map((hit, index) => (
        <li key={hit.chunk_id ?? `row-${index}`} className="result-card">
          <div className="result-card__meta">
            <span>
              {hit.score !== undefined && hit.score_kind !== undefined
                ? `Score ${formatScore(hit.score)}, ${scoreKindLabel(hit.score_kind)}`
                : "Not ranked: neighbour context"}
            </span>
            {hit.reranked ? <span>Reranked</span> : null}
            <span>{chunkPosition(hit.source_chunk_index, hit.source_chunk_count)}</span>
            {hit.page_label ? <span>Page {hit.page_label}</span> : null}
          </div>
          <div className="result-card__meta">
            <span className="text-code" dir="ltr">
              {hit.source}
            </span>
            <span className="availability" data-orphaned={String(availability(hit, sources))}>
              {availabilityLabel(availability(hit, sources))}
            </span>
          </div>
          <p className="server-text">{hit.text}</p>
          <div className="button-row">
            {hit.chunk_id !== null ? (
              <button type="button" className="button button--small" onClick={() => onShowChunk(hit.chunk_id!)}>
                Show chunk
              </button>
            ) : (
              <span className="text-meta">No stored chunk ID, so this row cannot be opened.</span>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
