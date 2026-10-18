import { ChevronDown, ChevronRight } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import type { AnswerResult, Citation, Evidence } from "../api/documents";
import { useAnswer } from "../api/mutations";
import { AlertNotice } from "../components/AlertNotice";
import { ErrorNotice } from "../components/ErrorNotice";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { AnswerText } from "./AnswerText";
import { answerStatus, failureLine } from "./answerStatus";
import { CitationPopover } from "./CitationPopover";
import { scoreText, sourceName } from "./citationText";

interface AssistantTurnProps {
  collection: string;
  question: string;
  /** The stored answer of a reopened chat. With one, the turn shows it and never asks the server. */
  saved?: AnswerResult | null;
  /** Called once for each answer that arrives from the server, so the view can store it. */
  onResult?: (result: AnswerResult) => void;
  onShowChunk: (collection: string, chunkId: string) => void;
}

/**
 * One assistant turn. It asks the collection the turn was sent to as soon as
 * it mounts, and owns its mutation, so Retry repeats only this question. A
 * turn with a stored answer shows it and asks nothing.
 */
export function AssistantTurn({ collection, question, saved = null, onResult, onShowChunk }: AssistantTurnProps) {
  const answer = useAnswer(collection);
  const { mutate } = answer;
  const started = useRef(false);
  useEffect(() => {
    if (started.current || saved !== null) return;
    started.current = true;
    mutate({ query: question });
  }, [mutate, question, saved]);

  const reported = useRef<AnswerResult | null>(null);
  useEffect(() => {
    if (answer.data === undefined || reported.current === answer.data) return;
    reported.current = answer.data;
    onResult?.(answer.data);
  }, [answer.data, onResult]);

  const retry = () => answer.mutate({ query: question });
  const result = saved ?? answer.data;
  const waiting = saved === null && (answer.isPending || answer.isIdle);

  return (
    <li className="flex flex-col gap-2">
      <p className="text-meta font-medium text-muted-foreground">Answer from {collection}</p>
      {saved === null && answer.isError ? <ErrorNotice error={answer.error} onRetry={retry} /> : null}
      {result?.status === "error" ? (
        <AlertNotice message={failureLine(result)}>
          <Button variant="outline" onClick={retry}>
            Retry
          </Button>
          {result.failure_stage === "generation" ? (
            <Button asChild variant="outline">
              <a href="#/settings/chat">Check the Chat model</a>
            </Button>
          ) : null}
        </AlertNotice>
      ) : null}
      {waiting ? (
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
      {result.answer !== null ? <AnswerText text={result.answer} citations={result.citations} evidence={result.evidence} collection={collection} onShowChunk={onShowChunk} /> : null}
      {result.unverified_claims && result.unverified_claims.length > 0 ? (
        <ul aria-label="Claims that failed verification" className="flex flex-col gap-1 text-meta">
          {result.unverified_claims.map((claim, index) => (
            <li key={index} className="break-words">
              {claim.claim} ({claim.verdict}, cites {claim.ordinals.map((n) => `[${n}]`).join(" ")})
            </li>
          ))}
        </ul>
      ) : null}
      <Citations citations={result.citations} evidence={result.evidence} collection={collection} onShowChunk={onShowChunk} />
      <EvidenceSection evidence={result.evidence} onShowChunk={show} />
    </>
  );
}

interface CitationsProps {
  citations: Citation[];
  evidence: Evidence[];
  collection: string;
  onShowChunk: (collection: string, chunkId: string) => void;
}

/** Only entries in `citations` become chips: markers in the answer text stay plain text, so no citation is invented. */
function Citations({ citations, evidence, collection, onShowChunk }: CitationsProps) {
  if (citations.length === 0) return <p className="text-meta text-muted-foreground">The server returned no citations.</p>;
  return (
    <ul aria-label="Citations" className="flex flex-wrap gap-2">
      {citations.map((citation) => (
        <li key={citation.ordinal}>
          {citation.chunk_id !== null ? (
            <CitationPopover
              citation={citation}
              evidence={evidence.find((e) => e.ordinal === citation.ordinal)}
              collection={collection}
              onShowChunk={onShowChunk}
              trigger={(props) => (
                <Button variant="chip" size="sm" dir="ltr" {...props}>
                  <span>[{citation.ordinal}]</span>
                  <span className="truncate">{sourceName(citation.source)}</span>
                </Button>
              )}
            />
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
