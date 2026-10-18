import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useApi } from "../api/ApiProvider";
import type { ChunkView } from "../api/documents";
import { chunkQuery } from "../api/queries";
import { ChunkMetadata } from "./ChunkMetadata";
import { ErrorNotice } from "./ErrorNotice";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "./ui/dialog";

interface ChunkViewerProps {
  collection: string;
  chunkId: string;
  onClose: () => void;
}

/**
 * Stored chunk evidence from the protected chunk route, with neighbour
 * navigation, in a dialog. It reads the index only; the original file is
 * never opened. Text is rendered as plain text, never as markup.
 */
export function ChunkViewer({ collection, chunkId, onClose }: ChunkViewerProps) {
  const api = useApi();
  const [current, setCurrent] = useState(chunkId);
  const [anchor, setAnchor] = useState(chunkId);
  if (anchor !== chunkId) {
    // A different citation or result was opened: start from it.
    setAnchor(chunkId);
    setCurrent(chunkId);
  }
  const query = useQuery(chunkQuery(api, collection, current, 1));
  const chunk = query.data?.chunk;
  const previous = query.data?.previous.at(-1);
  const next = query.data?.next[0];

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Stored chunk</DialogTitle>
          <DialogDescription>Read from the stored index. The original file is not opened.</DialogDescription>
        </DialogHeader>
        {query.isError ? <ErrorNotice error={query.error} onRetry={() => void query.refetch()} /> : null}
        {query.isPending ? <p role="status" className="text-meta text-muted-foreground">Loading the stored chunk.</p> : null}
        {chunk ? <ChunkBody chunk={chunk} /> : null}
        <DialogFooter className="sm:justify-start">
          <NeighbourButton label="Previous chunk" icon={<ChevronLeft aria-hidden="true" />} target={previous} onOpen={setCurrent} />
          <NeighbourButton label="Next chunk" icon={<ChevronRight aria-hidden="true" />} target={next} onOpen={setCurrent} />
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ChunkBody({ chunk }: { chunk: ChunkView }) {
  return (
    <>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-meta">
        <dt className="text-muted-foreground">Source</dt>
        <dd dir="ltr" className="font-mono text-code break-all">
          {chunk.source ?? "Unknown source"}
        </dd>
        <dt className="text-muted-foreground">Chunk ID</dt>
        <dd dir="ltr" className="font-mono text-code break-all">
          {chunk.chunk_id ?? "None"}
        </dd>
      </dl>
      <ChunkMetadata chunk={chunk} />
      <pre className="max-h-[50dvh] overflow-auto rounded-small border border-border bg-muted p-3 font-mono text-code whitespace-pre-wrap break-words">
        {chunk.text}
      </pre>
    </>
  );
}

function NeighbourButton({ label, icon, target, onOpen }: { label: string; icon: ReactNode; target: ChunkView | undefined; onOpen: (id: string) => void }) {
  const id = target?.chunk_id ?? null;
  return (
    <Button variant="outline" size="sm" disabled={id === null} onClick={() => id !== null && onOpen(id)}>
      {icon}
      {label}
    </Button>
  );
}
