import { Info } from "lucide-react";
import type { Citation, Evidence } from "../api/documents";
import { Button } from "../components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "../components/ui/tooltip";
import { CitationPopover } from "./CitationPopover";
import { scoreText, sourceName } from "./citationText";

interface CitationListProps {
  citations: Citation[];
  evidence: Evidence[];
  collection: string;
  onShowChunk: (collection: string, chunkId: string) => void;
}

/** Only entries in `citations` become chips: markers in the answer text stay plain text, so no citation is invented. */
export function CitationList({ citations, evidence, collection, onShowChunk }: CitationListProps) {
  if (citations.length === 0) return <p className="text-meta text-muted-foreground">The server returned no citations.</p>;
  return (
    <ul aria-label="Citations" className="flex flex-wrap gap-2">
      {citations.map((citation) => {
        const passage = evidence.find((e) => e.ordinal === citation.ordinal);
        return (
          <li key={citation.ordinal} className="min-w-0 max-w-full">
            {citation.chunk_id !== null ? (
              <div className="flex items-center gap-1">
                <div className="min-w-0">
                  <CitationPopover
                    citation={citation}
                    evidence={passage}
                    collection={collection}
                    onShowChunk={onShowChunk}
                    view="text"
                    trigger={(props) => (
                      <Button variant="chip" size="sm" dir="ltr" {...props}>
                        <span>[{citation.ordinal}]</span>
                        <span className="truncate">{sourceName(citation.source)}</span>
                      </Button>
                    )}
                  />
                </div>
                <CitationPopover
                  citation={citation}
                  evidence={passage}
                  collection={collection}
                  onShowChunk={onShowChunk}
                  view="details"
                  trigger={(props) => (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button variant="ghost" size="icon-sm" aria-label={`Lineage and metadata of citation ${citation.ordinal}`} {...props}>
                          <Info aria-hidden="true" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Lineage and metadata</TooltipContent>
                    </Tooltip>
                  )}
                />
              </div>
            ) : (
              <span className="text-meta text-muted-foreground">
                [{citation.ordinal}] {sourceName(citation.source)}: No stored chunk ID, so this citation cannot be opened.
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** The evidence the model was given, one row per chunk. */
export function EvidenceList({ evidence, collection, onShowChunk }: { evidence: Evidence[]; collection: string; onShowChunk: (collection: string, chunkId: string) => void }) {
  if (evidence.length === 0) return <p className="text-meta text-muted-foreground">No evidence was supplied for the latest answer.</p>;
  return (
    <ol aria-label="Evidence supplied to the model" className="flex flex-col gap-2">
      {evidence.map((item) => (
        <li key={item.ordinal} className="flex flex-col gap-1 rounded-small border border-border bg-card p-3">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-meta text-muted-foreground">
            <span className="font-semibold text-foreground">[{item.ordinal}]</span>
            <span dir="ltr" className="break-all font-mono text-code">
              {item.source ?? "Unknown source"}
            </span>
            {scoreText(item) ? <span>{scoreText(item)}</span> : null}
          </div>
          <div>
            {item.chunk_id !== null ? (
              <CitationPopover
                citation={item}
                evidence={item}
                collection={collection}
                onShowChunk={onShowChunk}
                view="text"
                trigger={(props) => (
                  <Button variant="outline" size="sm" aria-label={`Show passage for evidence ${item.ordinal}`} {...props}>
                    Show passage
                  </Button>
                )}
              />
            ) : (
              <span className="text-meta text-muted-foreground">No stored chunk ID, so this row cannot be opened.</span>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
