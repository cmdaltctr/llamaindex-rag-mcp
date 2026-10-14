import { useEffect, useState } from "react";
import type { FetchLike } from "../api/client";
import { getChunk, type ChunkView } from "../api/runs";
import { maskText } from "./redact";

interface ChunkViewerProps {
  collection: string;
  chunkId: string;
  fetchImpl?: FetchLike;
  onClose: () => void;
}

/** The full stored chunk from the protected chunk route, rendered as plain text. */
export function ChunkViewer({ collection, chunkId, fetchImpl, onClose }: ChunkViewerProps) {
  const [state, setState] = useState<{ chunk: ChunkView | null; error: string | null }>({ chunk: null, error: null });

  useEffect(() => {
    let live = true;
    getChunk(collection, chunkId, { fetchImpl }).then(
      (chunk) => live && setState({ chunk, error: null }),
      (error: unknown) => live && setState({ chunk: null, error: error instanceof Error ? error.message : String(error) }),
    );
    return () => {
      live = false;
    };
  }, [collection, chunkId, fetchImpl]);

  const record = state.chunk?.chunk;
  return (
    <section className="chunk-viewer" aria-label={`Chunk ${chunkId}`}>
      <div className="chunk-viewer__header">
        <h4>
          Chunk <code>{chunkId}</code>
        </h4>
        <button type="button" className="button button--ghost button--small" onClick={onClose}>
          Close chunk
        </button>
      </div>
      {state.error && <p className="type-meta">{`Could not open the chunk: ${maskText(state.error)}`}</p>}
      {!state.chunk && !state.error && <p className="type-meta">Loading the stored chunk.</p>}
      {record && (
        <>
          <p className="type-meta">
            {record.source ?? "Unknown source"}
            {typeof record.source_chunk_index === "number" ? `, chunk ${record.source_chunk_index}` : ""}
            {` in collection ${state.chunk!.collection}`}
          </p>
          <pre className="chunk-viewer__text">{record.text}</pre>
        </>
      )}
    </section>
  );
}
