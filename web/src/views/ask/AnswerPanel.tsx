import type { AnswerResult, Citation, Evidence } from "../../api/documents";
import { chunkPosition, formatScore, scoreKindLabel } from "../shared/labels";
import { answerStatus } from "./answerStatus";

interface AnswerPanelProps {
  result: AnswerResult;
  onShowChunk: (chunkId: string) => void;
}

function scoreText(item: Citation): string | null {
  if (item.score === null || item.score === undefined || !item.score_kind) return null;
  return `Score ${formatScore(item.score)}, ${scoreKindLabel(item.score_kind)}`;
}

/**
 * The answer, its status, the server's citations and the supplied evidence.
 * Only entries in `citations` become chunk links: citation markers in the
 * answer text stay plain text, so no citation is ever invented.
 */
export function AnswerPanel({ result, onShowChunk }: AnswerPanelProps) {
  const status = answerStatus(result);
  return (
    <section className="panel" aria-label="Answer">
      <div role="status" className="notice">
        <span className="answer-status" data-status={result.status}>
          {status.label}
        </span>
        <span>{status.meaning}</span>
      </div>
      {result.verification_skipped ? (
        <p className="notice notice--warning">
          Claim verification skipped: {result.verification_skipped}. Only the citation check applies.
        </p>
      ) : null}
      {result.answer !== null ? <p className="server-text">{result.answer}</p> : null}

      {result.unverified_claims && result.unverified_claims.length > 0 ? (
        <>
          <h2 className="text-section-title">Claims that failed verification</h2>
          <ul className="plain-list" aria-label="Claims that failed verification">
            {result.unverified_claims.map((claim, index) => (
              <li key={index} className="server-text">
                {claim.claim} ({claim.verdict}, cites {claim.ordinals.map((n) => `[${n}]`).join(" ")})
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <h2 className="text-section-title">Citations</h2>
      {result.citations.length === 0 ? (
        <p className="text-meta">The server returned no citations.</p>
      ) : (
        <ul className="plain-list" aria-label="Citations">
          {result.citations.map((citation) => (
            <CitationItem key={citation.ordinal} citation={citation} onShowChunk={onShowChunk} />
          ))}
        </ul>
      )}

      {result.evidence.length > 0 ? (
        <>
          <h2 className="text-section-title">Evidence supplied to the model</h2>
          <ol className="result-list" aria-label="Evidence supplied to the model">
            {result.evidence.map((item) => (
              <EvidenceItem key={item.ordinal} item={item} />
            ))}
          </ol>
        </>
      ) : null}
    </section>
  );
}

function CitationItem({ citation, onShowChunk }: { citation: Citation; onShowChunk: (chunkId: string) => void }) {
  const chunkId = citation.chunk_id;
  return (
    <li className="result-card">
      <div className="result-card__meta">
        <span>[{citation.ordinal}]</span>
        <span className="text-code" dir="ltr">
          {citation.source ?? "Unknown source"}
        </span>
        <span>{chunkPosition(citation.source_chunk_index, null)}</span>
        {scoreText(citation) ? <span>{scoreText(citation)}</span> : null}
      </div>
      {chunkId !== null ? (
        <button
          type="button"
          className="button button--small"
          aria-label={`Show chunk for citation ${citation.ordinal}`}
          onClick={() => onShowChunk(chunkId)}
        >
          Show chunk
        </button>
      ) : (
        <span className="text-meta">No stored chunk ID, so this citation cannot be opened.</span>
      )}
    </li>
  );
}

function EvidenceItem({ item }: { item: Evidence }) {
  return (
    <li className="result-card">
      <div className="result-card__meta">
        <span>[{item.ordinal}]</span>
        <span className="text-code" dir="ltr">
          {item.source ?? "Unknown source"}
        </span>
        {scoreText(item) ? <span>{scoreText(item)}</span> : null}
      </div>
      <p className="server-text">{item.text}</p>
    </li>
  );
}
