import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { useApi } from "../api/ApiProvider";
import type { Job } from "../api/documents";
import { rootsQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { IngestPanel } from "./IngestPanel";
import { UploadPanel } from "./UploadPanel";

interface AddSourcesProps {
  /** The open project, or `null` when the user is starting a new one. */
  active: string | null;
  onJob: (job: Job, label: string) => void;
}

/**
 * Upload and folder ingest into a named collection. The target defaults to the
 * open project; naming another collection, or a new one, starts a project
 * through its first ingest.
 */
export function AddSources({ active, onJob }: AddSourcesProps) {
  const targetId = useId();
  const roots = useQuery(rootsQuery(useApi()));
  const [target, setTarget] = useState("");
  const destination = target.trim() || active;

  return (
    <section aria-label="Add sources" className="flex flex-col gap-5">
      <div className="flex max-w-sm flex-col gap-1.5">
        <Label htmlFor={targetId}>Target collection</Label>
        <Input id={targetId} dir="ltr" value={target} placeholder={active ?? "papers"} onChange={(e) => setTarget(e.target.value)} />
        <p className="text-meta text-muted-foreground">
          {active !== null ? "Leave empty to add to this project." : "Name the collection to create. A new project starts with its first ingest."}
        </p>
      </div>
      {roots.isError ? <ErrorNotice error={roots.error} onRetry={() => void roots.refetch()} /> : null}
      <UploadPanel collection={destination} managedRoot={roots.data?.find((root) => root.kind === "managed")} onJob={onJob} />
      {roots.isError ? null : <IngestPanel collection={destination} roots={roots.data} onJob={onJob} />}
    </section>
  );
}
