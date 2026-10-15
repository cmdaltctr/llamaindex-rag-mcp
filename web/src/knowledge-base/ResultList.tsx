import type { DocumentInfo, SearchHit } from "../api/documents";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { availabilityLabel, chunkPosition, formatScore, scoreKindLabel } from "../lib/labels";

interface ResultListProps {
  hits: SearchHit[];
  sources: DocumentInfo[] | undefined;
  onShowChunk: (chunkId: string) => void;
}

/** Machine-local availability for a hit, matched by stable id, else by stored path. */
function availability(hit: SearchHit, sources: DocumentInfo[] | undefined): boolean | null {
  const match = sources?.find((s) => (hit.source_id !== null ? s.source_id === hit.source_id : s.source_id === null && s.source === hit.source));
  return match?.orphaned ?? null;
}

function availabilityVariant(orphaned: boolean | null) {
  return orphaned === true ? "warning" : orphaned === false ? "success" : "neutral";
}

/** Ranked chunks in the server's order, each with its score and score kind. */
export function ResultList({ hits, sources, onShowChunk }: ResultListProps) {
  return (
    <ol aria-label="Search results" className="flex flex-col gap-2">
      {hits.map((hit, index) => {
        const orphaned = availability(hit, sources);
        return (
          <li key={hit.chunk_id ?? `row-${index}`} className="flex flex-col gap-2 rounded-panel border border-border bg-card p-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-meta text-muted-foreground">
              <span className="font-semibold text-foreground">#{index + 1}</span>
              <span>
                {hit.score !== undefined && hit.score_kind !== undefined
                  ? `Score ${formatScore(hit.score)}, ${scoreKindLabel(hit.score_kind)}`
                  : "Not ranked: neighbour context"}
              </span>
              {hit.reranked ? <Badge variant="info">Reranked</Badge> : null}
              <span>{chunkPosition(hit.source_chunk_index, hit.source_chunk_count)}</span>
              {hit.page_label ? <span>Page {hit.page_label}</span> : null}
            </div>
            <div className="flex flex-wrap items-center gap-2 text-meta">
              <span dir="ltr" className="min-w-0 break-all font-mono text-code">
                {hit.source}
              </span>
              <Badge variant={availabilityVariant(orphaned)}>{availabilityLabel(orphaned)}</Badge>
            </div>
            <p className="whitespace-pre-wrap break-words">{hit.text}</p>
            <div>
              {hit.chunk_id !== null ? (
                <Button variant="outline" size="sm" onClick={() => onShowChunk(hit.chunk_id!)}>
                  Show chunk
                </Button>
              ) : (
                <span className="text-meta text-muted-foreground">No stored chunk ID, so this row cannot be opened.</span>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
