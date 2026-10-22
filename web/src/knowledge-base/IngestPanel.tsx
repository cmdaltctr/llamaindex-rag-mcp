import { FolderInput } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { ClientRefusal } from "../api/client";
import { joinRootPath, type Job, type Root } from "../api/documents";
import { useIngestPath } from "../api/mutations";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";

interface IngestPanelProps {
  /** The collection to ingest into; `null` until a project is open or named. */
  collection: string | null;
  /** `undefined` while the approved folders load. */
  roots: Root[] | undefined;
  onJob: (job: Job, label: string) => void;
}

/**
 * Ingest a file or folder inside a folder the operator approved at launch.
 * The browser sends only a root plus a relative path; it never names an
 * arbitrary server path.
 */
export function IngestPanel({ collection, roots, onJob }: IngestPanelProps) {
  const id = useId();
  const ingest = useIngestPath();
  const approved = (roots ?? []).filter((root) => root.kind === "operator");
  const [rootId, setRootId] = useState<string | null>(null);
  const [relative, setRelative] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const root = approved.find((candidate) => candidate.id === rootId) ?? approved[0];

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (root === undefined || collection === null) return;
    let path: string;
    try {
      path = joinRootPath(root.path, relative);
    } catch (error) {
      if (!(error instanceof ClientRefusal)) console.error(error);
      setProblem(error instanceof ClientRefusal ? error.message : "Enter a path inside the selected folder.");
      return;
    }
    setProblem(null);
    try {
      onJob(await ingest.mutateAsync({ path, collection }), relative.trim());
      setRelative("");
    } catch {
      // The mutation holds the error, which renders below.
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} aria-labelledby={`${id}-title`} className="flex flex-col gap-3">
      <h3 id={`${id}-title`} className="text-subsection-title font-semibold">
        Ingest from an approved folder
      </h3>
      {roots === undefined ? (
        <p role="status" className="text-meta text-muted-foreground">
          Loading approved folders.
        </p>
      ) : approved.length === 0 ? (
        <p className="text-meta text-muted-foreground">
          No folder is approved. Start the server with <code className="font-mono text-code">omrs web --root FOLDER</code> to approve one.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex w-full max-w-sm flex-col gap-1.5">
              <Label htmlFor={`${id}-root`}>Approved folder</Label>
              <Select value={root?.id} onValueChange={setRootId}>
                <SelectTrigger id={`${id}-root`} dir="ltr">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {approved.map((candidate) => (
                    <SelectItem key={candidate.id} value={candidate.id}>
                      {candidate.path}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex min-w-48 flex-1 flex-col gap-1.5">
              <Label htmlFor={`${id}-path`}>Path inside the folder</Label>
              <Input id={`${id}-path`} dir="ltr" value={relative} placeholder="reports/summary.md" onChange={(e) => setRelative(e.target.value)} />
            </div>
            <Button type="submit" disabled={collection === null || ingest.isPending}>
              <FolderInput aria-hidden="true" />
              Start ingest
            </Button>
          </div>
          {problem !== null ? (
            <p role="alert" className="text-ui text-status-error-label">
              {problem}
            </p>
          ) : null}
          {ingest.isError ? <ErrorNotice error={ingest.error} /> : null}
        </>
      )}
    </form>
  );
}
