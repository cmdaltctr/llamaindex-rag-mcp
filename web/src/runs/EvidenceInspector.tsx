import { useState } from "react";
import type { FetchLike } from "../api/client";
import { ChunkViewer } from "./ChunkViewer";
import { boundText, findEvidence, type Row } from "./evidence";
import { ChunkButton, EvidenceRows } from "./EvidenceRows";
import { maskText } from "./redact";

interface EvidenceInspectorProps {
  outputs: Record<string, unknown>;
  /** Used for a chunk link when the row does not name its collection. */
  fallbackCollection: string | null;
  fetchImpl?: FetchLike;
}

function Citations({ name, citations, onOpen }: { name: string; citations: Row[]; onOpen: (id: string, collection: string | null) => void }) {
  return (
    <ul className="citation-list" aria-label={`Citations: ${name}`}>
      {citations.map((citation, index) => (
        <li key={index}>
          <span>{`[${typeof citation.ordinal === "number" ? citation.ordinal : index + 1}] ${maskText(String(citation.source ?? "Unknown source"))}`}</span>{" "}
          <ChunkButton row={citation} onOpen={onOpen} />
        </li>
      ))}
    </ul>
  );
}

/** Bounded evidence from run outputs: ranked rows, citations and answers, each linked to its stored chunk. */
export function EvidenceInspector({ outputs, fallbackCollection, fetchImpl }: EvidenceInspectorProps) {
  const [open, setOpen] = useState<{ chunkId: string; collection: string | null } | null>(null);
  const items = findEvidence(outputs);
  const onOpen = (chunkId: string, collection: string | null) => setOpen({ chunkId, collection: collection ?? fallbackCollection });

  return (
    <section className="run-section" aria-label="Evidence">
      <h3>Evidence</h3>
      <p className="type-meta">
        Each score keeps its own kind. Scores of different kinds are not comparable and are not probabilities of correctness.
      </p>
      {items.length === 0 && <p className="type-meta">No ranked rows, citations or answers were found in the run outputs.</p>}
      {items.map((item) => (
        <div key={`${item.kind}-${item.name}`} className="evidence-item">
          <h4>
            <code>{item.name}</code>
          </h4>
          {item.kind === "rows" && <EvidenceRows name={item.name} rows={item.rows} total={item.total} onOpen={onOpen} />}
          {item.kind === "citations" && <Citations name={item.name} citations={item.citations} onOpen={onOpen} />}
          {item.kind === "answer" && <p className="evidence-answer">{boundText(maskText(item.text)).text}</p>}
        </div>
      ))}
      {open &&
        (open.collection ? (
          <ChunkViewer key={open.chunkId} collection={open.collection} chunkId={open.chunkId} fetchImpl={fetchImpl} onClose={() => setOpen(null)} />
        ) : (
          <p className="type-meta">{`The collection of chunk ${open.chunkId} is not recorded, so the chunk cannot be opened.`}</p>
        ))}
    </section>
  );
}

