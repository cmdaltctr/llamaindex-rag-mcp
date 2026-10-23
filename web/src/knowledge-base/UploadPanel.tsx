import { useQuery } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { useApi } from "../api/ApiProvider";
import { ApiError } from "../api/client";
import { joinRootPath, type Job, type Root } from "../api/documents";
import { useIngestPath, useUploadFile } from "../api/mutations";
import { uploadLimitQuery } from "../api/queries";
import { Button } from "../components/ui/button";
import { describeError } from "../lib/errors";
import { formatMiB } from "../lib/uploadLimit";
import { FileDropZone } from "./FileDropZone";

interface UploadPanelProps {
  /** The collection to ingest into; `null` until a project is open or named. */
  collection: string | null;
  managedRoot: Root | undefined;
  onJob: (job: Job, label: string) => void;
}

/**
 * Plain words for the rejections the server reports for one file: bad name,
 * too large, or unsupported type. `limit` is the label of the limit the server
 * reported, or `null` when it could not be read, so no number is invented.
 */
function rejection(error: unknown, limit: string | null): string {
  if (error instanceof ApiError && error.kind === "http") {
    if (error.status === 413) return `rejected. The file is larger than ${limit === null ? "the server's per-file limit" : `the ${limit} limit`}.`;
    if (error.status === 415) return "rejected. That file type cannot be ingested.";
    if (error.status === 400) return "rejected. The server did not accept that file name.";
  }
  return `failed. ${describeError(error).message}`;
}

/**
 * Upload ordinary files into workspace-managed storage, then queue their
 * ingestion by managed-root path. The limit comes from the server only. A
 * file over it is refused here and never sent; when the limit cannot be read,
 * the server's own check is the only one. The server checks name, size and
 * type again before the bytes.
 */
export function UploadPanel({ collection, managedRoot, onJob }: UploadPanelProps) {
  const inputId = useId();
  const upload = useUploadFile();
  const ingest = useIngestPath();
  const maxBytes = useQuery(uploadLimitQuery(useApi())).data?.max_bytes ?? null;
  const limit = maxBytes === null ? null : formatMiB(maxBytes);
  const [files, setFiles] = useState<File[]>([]);
  const [results, setResults] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function uploadOne(file: File, target: string): Promise<string> {
    if (maxBytes !== null && file.size > maxBytes) {
      return `${file.name}: not sent. The file is ${formatMiB(file.size)}. The limit is ${limit} per file.`;
    }
    let record;
    try {
      record = await upload.mutateAsync(file);
    } catch (error) {
      return `${file.name}: ${rejection(error, limit)}`;
    }
    if (managedRoot === undefined) return `${file.name}: uploaded, but no managed folder is available to ingest it.`;
    try {
      const job = await ingest.mutateAsync({ path: joinRootPath(managedRoot.path, `${record.id}/${record.name}`), collection: target });
      onJob(job, record.name);
      return `${file.name}: uploaded, ingestion queued into ${target}.`;
    } catch (error) {
      return `${file.name}: uploaded, but ingestion was not queued. ${describeError(error).message}`;
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (collection === null) return;
    setBusy(true);
    const lines: string[] = [];
    for (const file of files) {
      // One at a time keeps the server's single job queue and the size checks predictable.
      lines.push(await uploadOne(file, collection));
      setResults([...lines]);
    }
    // The results list replaces the chosen files, so a second click cannot send them again.
    setFiles([]);
    setBusy(false);
  }

  return (
    <form onSubmit={(e) => void submit(e)} aria-labelledby={`${inputId}-title`} className="flex flex-col gap-3">
      <h3 id={`${inputId}-title`} className="text-subsection-title font-semibold">
        Upload files
      </h3>
      <p className="text-meta text-muted-foreground">
        {limit !== null ? `Limit: ${limit} per file. A larger file is refused here and never sent. ` : null}
        The server checks each file's name, size and type before the file is sent. Archives and web addresses are not accepted.
      </p>
      <FileDropZone files={files} onChange={setFiles} disabled={busy} />
      <div>
        <Button type="submit" disabled={busy || files.length === 0 || collection === null}>
          <Upload aria-hidden="true" />
          Upload and ingest
        </Button>
      </div>
      {busy ? (
        <p role="status" className="text-meta text-muted-foreground">
          Uploading.
        </p>
      ) : null}
      {results.length > 0 ? (
        <ul aria-label="Upload results" className="flex flex-col gap-1 text-meta">
          {results.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
        </ul>
      ) : null}
    </form>
  );
}
