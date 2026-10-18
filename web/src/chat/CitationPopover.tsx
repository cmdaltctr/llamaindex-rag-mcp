import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useApi } from "../api/ApiProvider";
import type { ChunkView, Citation, Evidence } from "../api/documents";
import { chunkQuery } from "../api/queries";
import { ChunkMetadata } from "../components/ChunkMetadata";
import { Button } from "../components/ui/button";
import { Popover, type PopoverTriggerProps } from "../components/ui/popover";
import { scoreText, sourceName } from "./citationText";

interface CitationPopoverProps {
  citation: Citation;
  /** The evidence row with the same ordinal, when the answer carries one. */
  evidence: Evidence | undefined;
  collection: string;
  onShowChunk: (collection: string, chunkId: string) => void;
  /** The chip or the `[n]` marker that opens the popover. */
  trigger: (props: PopoverTriggerProps) => ReactNode;
}

/** What the citation itself knows, shown at once while the stored chunk loads. */
function fromCitation(citation: Citation): ChunkView {
  return {
    chunk_id: citation.chunk_id,
    source_id: citation.source_id,
    source_version: citation.source_version,
    source_chunk_index: citation.source_chunk_index,
    source_chunk_count: null,
    source: citation.source,
    page_label: null,
    text: "",
    metadata: {},
  };
}

/** Opens next to a citation chip or marker: the evidence text, the lineage and the stored metadata. */
export function CitationPopover({ citation, evidence, collection, onShowChunk, trigger }: CitationPopoverProps) {
  return (
    <Popover slot="citation-popover-content" width={352} className="max-h-[70dvh] overflow-auto" trigger={trigger}>
      {({ close }) => (
        <PopoverBody
          citation={citation}
          evidence={evidence}
          collection={collection}
          onOpenChunk={(chunkId) => {
            close();
            onShowChunk(collection, chunkId);
          }}
        />
      )}
    </Popover>
  );
}

interface PopoverBodyProps {
  citation: Citation;
  evidence: Evidence | undefined;
  collection: string;
  onOpenChunk: (chunkId: string) => void;
}

function PopoverBody({ citation, evidence, collection, onOpenChunk }: PopoverBodyProps) {
  const api = useApi();
  const chunkId = citation.chunk_id;
  const query = useQuery({ ...chunkQuery(api, collection, chunkId ?? "", 1), enabled: chunkId !== null, retry: false });
  const stored = query.data?.chunk;
  const unavailable = chunkId === null || query.isError;
  const score = scoreText(citation);
  return (
    <>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="font-semibold">[{citation.ordinal}]</span>
        <span dir="ltr" className="min-w-0 break-all font-mono text-code">
          {sourceName(citation.source)}
        </span>
      </div>
      {score !== null ? <p className="text-muted-foreground">{score}</p> : null}
      {evidence !== undefined ? <p className="whitespace-pre-wrap break-words">{evidence.text}</p> : null}
      <ChunkMetadata chunk={stored ?? fromCitation(citation)} chunkIds={citation.chunk_ids} showMetadata={stored !== undefined} />
      {unavailable ? <p className="text-muted-foreground">The stored chunk is not available.</p> : null}
      {chunkId !== null && query.isPending ? (
        <p role="status" className="text-muted-foreground">
          Loading the stored metadata.
        </p>
      ) : null}
      {chunkId !== null && !unavailable ? (
        <div>
          <Button variant="outline" size="sm" onClick={() => onOpenChunk(chunkId)}>
            Open full chunk
          </Button>
        </div>
      ) : null}
    </>
  );
}
