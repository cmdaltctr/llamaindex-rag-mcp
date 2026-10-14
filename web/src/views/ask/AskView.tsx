import { useId, useState, type FormEvent } from "react";
import type { FetchLike } from "../../api/client";
import { answerCollection, listCollections, type AnswerResult } from "../../api/documents";
import { ChunkViewer } from "../shared/ChunkViewer";
import { CollectionSelect, ErrorNotice, ViewHeader } from "../shared/controls";
import { messageOf } from "../shared/labels";
import { useLoad } from "../shared/useLoad";
import { AnswerPanel } from "./AnswerPanel";

interface AskViewProps {
  fetchImpl?: FetchLike;
  focusHeading?: boolean;
}

const MAX_QUESTION = 4096;

/** Cited answering through the shared core path. Controls stay with the collection profile. */
export function AskView({ fetchImpl, focusHeading = false }: AskViewProps) {
  const id = useId();
  const collections = useLoad(() => listCollections({ fetchImpl }), "collections");
  const [selected, setSelected] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<{ collection: string; result: AnswerResult } | null>(null);
  const [chunkId, setChunkId] = useState<string | null>(null);
  const active = collections.data?.find((c) => c.name === selected)?.name ?? collections.data?.[0]?.name ?? null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (active === null) return;
    if (question.trim() === "") {
      setError("Enter a question.");
      return;
    }
    setBusy(true);
    setError(null);
    setChunkId(null);
    try {
      setAnswer({ collection: active, result: await answerCollection(active, { query: question }, { fetchImpl }) });
    } catch (problem) {
      setAnswer(null);
      setError(messageOf(problem));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="view view--documents" aria-labelledby="view-ask-title">
      <ViewHeader id="ask" focusHeading={focusHeading} />
      <ErrorNotice message={collections.error} />
      <form className="panel" onSubmit={(e) => void submit(e)} aria-label="Ask a question">
        <CollectionSelect collections={collections.data} value={active} onChange={setSelected} />
        <div className="field">
          <label className="field__label" htmlFor={id}>
            Question
          </label>
          <textarea
            id={id}
            className="control"
            rows={3}
            maxLength={MAX_QUESTION}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
        </div>
        <p className="field__hint">Retrieval controls use the collection profile.</p>
        <ErrorNotice message={error} />
        <div className="button-row">
          <button type="submit" className="button button--tinted" disabled={busy || active === null}>
            Ask
          </button>
        </div>
      </form>
      {answer === null ? (
        <div className="empty-state" data-testid="empty-state">
          <p className="empty-state__title">{busy ? "Waiting for the answer" : "No question yet"}</p>
          <p className="type-meta">The answer appears here with its status, citations and evidence.</p>
        </div>
      ) : (
        <AnswerPanel result={answer.result} onShowChunk={setChunkId} />
      )}
      {answer !== null && chunkId !== null ? (
        <ChunkViewer collection={answer.collection} chunkId={chunkId} fetchImpl={fetchImpl} onClose={() => setChunkId(null)} />
      ) : null}
    </section>
  );
}
