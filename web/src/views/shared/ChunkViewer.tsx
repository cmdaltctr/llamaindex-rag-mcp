import { useState } from "react";
import type { FetchLike } from "../../api/client";
import { getChunk, type ChunkView } from "../../api/documents";
import { ErrorNotice } from "./controls";
import { chunkPosition } from "./labels";
import { useLoad } from "./useLoad";

interface ChunkViewerProps {
  collection: string;
  chunkId: string;
  fetchImpl?: FetchLike;
  onClose: () => void;
}

/**
 * Stored chunk evidence from the protected chunk route, with neighbour
 * navigation. It reads the index only; the original file is never opened.
 * Text is rendered as plain text.
 */
export function ChunkViewer({ collection, chunkId, fetchImpl, onClose }: ChunkViewerProps) {
  const [current, setCurrent] = useState(chunkId);
  const [anchor, setAnchor] = useState(chunkId);
  if (anchor !== chunkId) {
    // A different citation or result was opened: start from it.
    setAnchor(chunkId);
    setCurrent(chunkId);
  }
  const { data, error, loading } = useLoad(() => getChunk(collection, current, 1, { fetchImpl }), `${collection}/${current}`);
  const chunk = data?.chunk;
  const previous = data?.previous.at(-1);
  const next = data?.next[0];

  return (
    <section className="panel chunk-viewer" aria-label="Stored chunk">
      <header className="panel__header">
        <h2 className="type-section-title">Stored chunk</h2>
        <button type="button" className="button button--ghost button--small" onClick={onClose}>
          Close
        </button>
      </header>
      <ErrorNotice message={error} />
      {loading && chunk === undefined ? <p className="type-meta">Loading the stored chunk.</p> : null}
      {chunk ? <ChunkBody chunk={chunk} /> : null}
      <div className="button-row">
        <NeighbourButton label="Previous chunk" target={previous} onOpen={setCurrent} />
        <NeighbourButton label="Next chunk" target={next} onOpen={setCurrent} />
      </div>
      <p className="type-meta">Read from the stored index. The original file is not opened.</p>
    </section>
  );
}

function ChunkBody({ chunk }: { chunk: ChunkView }) {
  return (
    <>
      <dl className="facts">
        <dt>Source</dt>
        <dd className="type-code" dir="ltr">
          {chunk.source ?? "Unknown source"}
        </dd>
        <dt>Position</dt>
        <dd>
          {chunkPosition(chunk.source_chunk_index, chunk.source_chunk_count)}
          {chunk.page_label !== null ? `, Page ${chunk.page_label}` : ""}
        </dd>
        <dt>Chunk ID</dt>
        <dd className="type-code" dir="ltr">
          {chunk.chunk_id ?? "None"}
        </dd>
      </dl>
      <pre className="chunk-text">{chunk.text}</pre>
    </>
  );
}

function NeighbourButton({ label, target, onOpen }: { label: string; target: ChunkView | undefined; onOpen: (id: string) => void }) {
  const id = target?.chunk_id ?? null;
  return (
    <button type="button" className="button button--small" disabled={id === null} onClick={() => id !== null && onOpen(id)}>
      {label}
    </button>
  );
}
