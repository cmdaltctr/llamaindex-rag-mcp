import type { Citation, Evidence } from "../api/documents";
import { Button } from "../components/ui/button";
import { CitationPopover } from "./CitationPopover";

interface AnswerTextProps {
  text: string;
  citations: Citation[];
  evidence: Evidence[];
  collection: string;
  onShowChunk: (collection: string, chunkId: string) => void;
}

/**
 * The answer as plain text. A `[n]` marker becomes a button only when `n` is the
 * ordinal of a returned citation, so no citation is invented. Any other marker
 * stays text. The text is never rendered as markup.
 */
export function AnswerText({ text, citations, evidence, collection, onShowChunk }: AnswerTextProps) {
  const parts = text.split(/\[(\d+)\]/);
  return (
    <p className="whitespace-pre-wrap break-words">
      {parts.map((part, index) => {
        if (index % 2 === 0) return part;
        const citation = citations.find((c) => c.ordinal === Number(part));
        if (citation === undefined) return `[${part}]`;
        return (
          <CitationPopover
            key={index}
            citation={citation}
            evidence={evidence.find((e) => e.ordinal === citation.ordinal)}
            collection={collection}
            onShowChunk={onShowChunk}
            trigger={(props) => (
              <Button variant="link" size="inline" dir="ltr" aria-label={`Citation ${citation.ordinal}`} className="align-baseline" {...props}>
                [{part}]
              </Button>
            )}
          />
        );
      })}
    </p>
  );
}
