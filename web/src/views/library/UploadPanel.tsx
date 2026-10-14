import { useId, useState, type FormEvent } from "react";
import { ApiError, type FetchLike } from "../../api/client";
import { ingestPath, joinRootPath, uploadFile, type Job, type Root } from "../../api/documents";
import { messageOf } from "../shared/labels";

interface UploadPanelProps {
  collection: string;
  managedRoot: Root | undefined;
  fetchImpl?: FetchLike;
  onJob: (job: Job, label: string) => void;
}

/** Rejections the server reports for one file: bad name, too large, or unsupported type. */
function isRejection(error: unknown): boolean {
  return error instanceof ApiError && error.kind === "http" && [400, 413, 415].includes(error.status ?? 0);
}

/**
 * Upload ordinary files into workspace-managed storage, then queue their
 * ingestion by managed-root path. The server checks each file's name, size
 * and type before the bytes are sent and reports a reason per file.
 */
export function UploadPanel({ collection, managedRoot, fetchImpl, onJob }: UploadPanelProps) {
  const inputId = useId();
  const [files, setFiles] = useState<File[]>([]);
  const [results, setResults] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function uploadOne(file: File): Promise<string> {
    let record;
    try {
      record = await uploadFile(file, { fetchImpl });
    } catch (error) {
      return `${file.name}: ${isRejection(error) ? "rejected" : "failed"}. ${messageOf(error)}`;
    }
    if (managedRoot === undefined) {
      return `${file.name}: uploaded, but no managed folder is available to ingest it.`;
    }
    try {
      const job = await ingestPath(joinRootPath(managedRoot.path, `${record.id}/${record.name}`), collection, { fetchImpl });
      onJob(job, record.name);
      return `${file.name}: uploaded, ingestion queued into ${collection}.`;
    } catch (error) {
      return `${file.name}: uploaded, but ingestion was not queued. ${messageOf(error)}`;
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    const lines: string[] = [];
    for (const file of files) {
      // One at a time keeps the server's single job queue and the size checks predictable.
      lines.push(await uploadOne(file));
      setResults([...lines]);
    }
    setBusy(false);
  }

  return (
    <form className="panel" onSubmit={(e) => void submit(e)} aria-labelledby={`${inputId}-title`}>
      <h2 id={`${inputId}-title`} className="type-section-title">
        Upload files
      </h2>
      <p className="type-meta">
        Limit: 50 MiB per file. The server checks each file's name, size and type before the file is sent. Archives and web
        addresses are not accepted.
      </p>
      <div className="field">
        <label className="field__label" htmlFor={inputId}>
          Files to upload
        </label>
        <input
          id={inputId}
          className="control control--file"
          type="file"
          multiple
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
      </div>
      <button type="submit" className="button button--tinted" disabled={busy || files.length === 0}>
        Upload and ingest
      </button>
      {results.length > 0 ? (
        <ul className="result-lines" aria-label="Upload results">
          {results.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
        </ul>
      ) : null}
    </form>
  );
}
