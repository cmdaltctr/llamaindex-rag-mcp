import { ChevronDown, ChevronRight } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import type { AnswerResult, Citation, Evidence } from "../api/documents";
import { useAnswer } from "../api/mutations";
import { AlertNotice } from "../components/AlertNotice";
import { ErrorNotice } from "../components/ErrorNotice";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { formatScore, scoreKindLabel } from "../lib/labels";
import { answerStatus, failureLine } from "./answerStatus";

interface AssistantTurnProps {
  collection: string;
  question: string;
  onShowChunk: (collection: string, chunkId: string) => void;
}

function scoreText(item: Citation): string | null {
  if (item.score === null || item.score === undefined || !item.score_kind) return null;
  return `Score ${formatScore(item.score)}, ${scoreKindLabel(item.score_kind)}`;
}

/** The last path segment, so a chip stays short. The full source shows in the chunk viewer. */
function sourceName(source: string | null): string {
  if (source === null) return "Unknown source";
  return source.split(/[/\\]/).filter(Boolean).at(-1) ?? source;
}

/**
 * One assistant turn. It asks the collection the turn was sent to as soon as
 * it mounts, and owns its mutation, so Retry repeats only this question.
 */
export function AssistantTurn({ collection, question, onShowChunk }: AssistantTurnProps) {
  const answer = useAnswer(collection);
  const { mutate } = answer;
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    mutate({ query: question });
  }, [mutate, question]);

  const retry = () => answer.mutate({ query: question });
  const result = answer.data;

  return (
    <li className="flex flex-col gap-2">
      <p className="text-meta font-medium text-muted-foreground">Answer from {collection}</p>
      {answer.isError ? <ErrorNotice error={answer.error} onRetry={retry} /> : null}
      {result?.status === "error" ? (
        <AlertNotice message={failureLine(result)}>
          <Button variant="outline" onClick={retry}>
            Retry
          </Button>
        </AlertNotice>
      ) : null}
      {answer.isPending || answer.isIdle ? (
        <p role="status" className="text-meta text-muted-foreground">
          Waiting for the answer.
        </p>
      ) : null}
      {result && result.status !== "error" ? <AnswerBody result={result} collection={collection} onShowChunk={onShowChunk} /> : null}
    </li>
  );
}

function AnswerBody({ result, collection, onShowChunk }: { result: AnswerResult; collection: string; onShowChunk: AssistantTurnProps["onShowChunk"] }) {
  const status = answerStatus(result);
  const show = (chunkId: string) => onShowChunk(collection, chunkId);
  return (
    <>
      <div className="flex flex-col items-start gap-1">
        <Badge variant={status.variant}>{status.label}</Badge>
        <p className="text-meta text-muted-foreground">{status.meaning}</p>
      </div>
      {result.verification_skipped ? (
        <p className="text-meta text-status-warning-label">
          Claim verification skipped: {result.verification_skipped}. Only the citation check applies.
        </p>
      ) : null}
      {result.answer !== null ? <p className="whitespace-pre-wrap break-words">{result.answer}</p> : null}
      {result.unverified_claims && result.unverified_claims.length > 0 ? (
        <ul aria-label="Claims that failed verification" className="flex flex-col gap-1 text-meta">
          {result.unverified_claims.map((claim, index) => (
            <li key={index} className="break-words">
              {claim.claim} ({claim.verdict}, cites {claim.ordinals.map((n) => `[${n}]`).join(" ")})
            </li>
          ))}
        </ul>
      ) : null}
      <Citations citations={result.citations} onShowChunk={show} />
      <EvidenceSection evidence={result.evidence} onShowChunk={show} />
    </>
  );
}

/** Only entries in `citations` become chips: markers in the answer text stay plain text, so no citation is invented. */
function Citations({ citations, onShowChunk }: { citations: Citation[]; onShowChunk: (chunkId: string) => void }) {
  if (citations.length === 0) return <p className="text-meta text-muted-foreground">The server returned no citations.</p>;
  return (
    <ul aria-label="Citations" className="flex flex-wrap gap-2">
      {citations.map((citation) => (
        <li key={citation.ordinal}>
          {citation.chunk_id !== null ? (
            <Button variant="chip" size="sm" dir="ltr" onClick={() => onShowChunk(citation.chunk_id!)}>
              <span>[{citation.ordinal}]</span>
              <span className="truncate">{sourceName(citation.source)}</span>
            </Button>
          ) : (
            <span className="text-meta text-muted-foreground">
              [{citation.ordinal}] {sourceName(citation.source)}: No stored chunk ID, so this citation cannot be opened.
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

function EvidenceSection({ evidence, onShowChunk }: { evidence: Evidence[]; onShowChunk: (chunkId: string) => void }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  if (evidence.length === 0) return null;
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <div className="flex flex-col gap-2">
      <div>
        <Button variant="ghost" size="sm" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
          <Chevron aria-hidden="true" />
          Evidence ({evidence.length})
        </Button>
      </div>
      {open ? (
        <ol id={id} aria-label="Evidence supplied to the model" className="flex flex-col gap-2">
          {evidence.map((item) => (
            <li key={item.ordinal} className="flex flex-col gap-1 rounded-small border border-border bg-card p-3">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-meta text-muted-foreground">
                <span className="font-semibold text-foreground">[{item.ordinal}]</span>
                <span dir="ltr" className="break-all font-mono text-code">
                  {item.source ?? "Unknown source"}
                </span>
                {scoreText(item) ? <span>{scoreText(item)}</span> : null}
              </div>
              <p className="whitespace-pre-wrap break-words">{item.text}</p>
              <div>
                {item.chunk_id !== null ? (
                  <Button variant="outline" size="sm" aria-label={`Show chunk for evidence ${item.ordinal}`} onClick={() => onShowChunk(item.chunk_id!)}>
                    Show chunk
                  </Button>
                ) : (
                  <span className="text-meta text-muted-foreground">No stored chunk ID, so this row cannot be opened.</span>
                )}
              </div>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
