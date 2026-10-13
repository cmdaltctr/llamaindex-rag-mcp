import { useId, useState, type FormEvent } from "react";
import type { FetchLike } from "../../api/client";
import { ingestPath, joinRootPath, type Job, type Root } from "../../api/documents";
import { ErrorNotice } from "../shared/controls";
import { messageOf } from "../shared/labels";

interface IngestPanelProps {
  collection: string;
  roots: Root[];
  fetchImpl?: FetchLike;
  onJob: (job: Job, label: string) => void;
}

/**
 * Ingest a file or folder inside a folder the operator approved at launch.
 * The browser sends only a root plus a relative path; it never names an
 * arbitrary server path.
 */
export function IngestPanel({ collection, roots, fetchImpl, onJob }: IngestPanelProps) {
  const id = useId();
  const approved = roots.filter((root) => root.kind === "operator");
  const [rootId, setRootId] = useState<string | null>(null);
  const [relative, setRelative] = useState("");
  const [error, setError] = useState<string | null>(null);
  const root = approved.find((candidate) => candidate.id === rootId) ?? approved[0];

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (root === undefined) return;
    let path: string;
    try {
      path = joinRootPath(root.path, relative);
    } catch (problem) {
      setError(messageOf(problem));
      return;
    }
    setError(null);
    try {
      onJob(await ingestPath(path, collection, { fetchImpl }), relative.trim());
      setRelative("");
    } catch (problem) {
      setError(messageOf(problem));
    }
  }

  return (
    <form className="panel" onSubmit={(e) => void submit(e)} aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="text-section-title">
        Ingest from an approved folder
      </h2>
      {approved.length === 0 ? (
        <p className="text-meta">No folders are approved. Start the server with omrg web --root FOLDER to approve one.</p>
      ) : (
        <>
          <div className="form-row">
            <div className="field">
              <label className="field__label" htmlFor={`${id}-root`}>
                Approved folder
              </label>
              <select id={`${id}-root`} className="control control--select" value={root?.id} onChange={(e) => setRootId(e.target.value)}>
                {approved.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.path}
                  </option>
                ))}
              </select>
            </div>
            <div className="field field--grow">
              <label className="field__label" htmlFor={`${id}-path`}>
                Path inside the folder
              </label>
              <input
                id={`${id}-path`}
                className="control"
                dir="ltr"
                value={relative}
                placeholder="reports/summary.md"
                onChange={(e) => setRelative(e.target.value)}
              />
            </div>
            <button type="submit" className="button button--tinted">
              Ingest
            </button>
          </div>
          <ErrorNotice message={error} />
        </>
      )}
    </form>
  );
}
