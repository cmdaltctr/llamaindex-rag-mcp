import { useState } from "react";
import { ChunkViewer } from "../../components/ChunkViewer";
import { boundText, findEvidence, type Row } from "../../runs/evidence";
import { maskText } from "../../runs/redact";
import { Panel } from "../Panel";
import { ChunkButton, EvidenceRows } from "./EvidenceRows";
import { OpenFullOutput } from "./OutputViewer";

interface EvidenceInspectorProps {
  runId: string;
  outputs: Record<string, unknown>;
  /** Used for a chunk link when the row does not name its collection. */
  fallbackCollection: string | null;
}

interface CitationsProps {
  runId: string;
  name: string;
  citations: Row[];
  total: number;
  all: Row[];
  onOpen: (id: string, collection: string | null) => void;
}

function Citations({ runId, name, citations, total, all, onOpen }: CitationsProps) {
  return (
    <>
      {total > citations.length && (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-meta text-muted-foreground">{`Showing the first ${citations.length} of ${total} citations.`}</p>
          <OpenFullOutput runId={runId} name={name} source={{ value: all }} />
        </div>
      )}
      <ul aria-label={`Citations: ${name}`} className="flex flex-col gap-2">
        {citations.map((citation, index) => (
          <li key={index} className="flex flex-wrap items-center gap-2">
            <span className="[overflow-wrap:anywhere]">{`[${typeof citation.ordinal === "number" ? citation.ordinal : index + 1}] ${maskText(String(citation.source ?? "Unknown source"))}`}</span>
            <ChunkButton row={citation} onOpen={onOpen} />
          </li>
        ))}
      </ul>
    </>
  );
}

/** An answer, cut at 4 KiB for display, with its full text one action away. */
function Answer({ runId, name, text }: { runId: string; name: string; text: string }) {
  const preview = boundText(maskText(text));
  return (
    <div className="flex flex-col gap-2">
      <p className="whitespace-pre-wrap [overflow-wrap:anywhere]">{preview.text}</p>
      {preview.truncated && (
        <div className="flex flex-wrap items-center gap-2 text-meta text-muted-foreground">
          <span>Preview cut at 4 KiB.</span>
          <OpenFullOutput runId={runId} name={name} source={{ value: text }} />
        </div>
      )}
    </div>
  );
}

/** Bounded evidence from run outputs: ranked rows, citations and answers, each linked to its stored chunk. */
export function EvidenceInspector({ runId, outputs, fallbackCollection }: EvidenceInspectorProps) {
  const [open, setOpen] = useState<{ chunkId: string; collection: string | null } | null>(null);
  const items = findEvidence(outputs);
  const onOpen = (chunkId: string, collection: string | null) => setOpen({ chunkId, collection: collection ?? fallbackCollection });

  return (
    <Panel title="Evidence" level={3} description="Each score keeps its own kind. Scores of different kinds are not comparable and are not probabilities of correctness.">
      {items.length === 0 && <p className="text-meta text-muted-foreground">No ranked rows, citations or answers were found in the run outputs.</p>}
      {items.map((item) => (
        <div key={`${item.kind}-${item.name}`} className="flex flex-col gap-2">
          <h4 className="text-subsection-title font-semibold">
            <code className="font-mono text-code">{item.name}</code>
          </h4>
          {item.kind === "rows" && <EvidenceRows runId={runId} name={item.name} rows={item.rows} total={item.total} all={item.all} onOpen={onOpen} />}
          {item.kind === "citations" && <Citations runId={runId} name={item.name} citations={item.citations} total={item.total} all={item.all} onOpen={onOpen} />}
          {item.kind === "answer" && <Answer runId={runId} name={item.name} text={item.text} />}
        </div>
      ))}
      {open &&
        (open.collection ? (
          <ChunkViewer key={open.chunkId} collection={open.collection} chunkId={open.chunkId} onClose={() => setOpen(null)} />
        ) : (
          <p className="text-meta text-muted-foreground">{`The collection of chunk ${open.chunkId} is not recorded, so the chunk cannot be opened.`}</p>
        ))}
    </Panel>
  );
}
