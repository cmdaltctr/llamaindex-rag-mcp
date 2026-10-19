import type { Job } from "../api/documents";
import { useIngestJob } from "../api/mutations";
import { ErrorNotice } from "../components/ErrorNotice";
import { Badge } from "../components/ui/badge";
import { jobOutcome } from "./jobOutcome";

export interface TrackedJob {
  job: Job;
  label: string;
}

/** Ingestion jobs this page started, polled until they finish. */
export function JobList({ jobs }: { jobs: TrackedJob[] }) {
  if (jobs.length === 0) return null;
  return (
    <ul aria-label="Jobs" className="flex flex-col gap-2">
      {jobs.map((tracked) => (
        <JobItem key={tracked.job.job_id} tracked={tracked} />
      ))}
    </ul>
  );
}

function JobItem({ tracked }: { tracked: TrackedJob }) {
  const query = useIngestJob(tracked.job.job_id);
  const outcome = jobOutcome(query.data ?? tracked.job);
  return (
    <li className="flex flex-wrap items-center gap-2 rounded-small border border-border bg-card px-3 py-2">
      <span dir="ltr" className="min-w-0 break-all font-mono text-code">
        {tracked.label}
      </span>
      <Badge variant={outcome.variant} role="status">
        {outcome.text}
      </Badge>
      {outcome.detail === null ? null : (
        <span className={outcome.variant === "warning" ? "text-meta text-status-warning-label" : "text-meta text-status-error-label"}>{outcome.detail}</span>
      )}
      {query.isError ? <ErrorNotice error={query.error} onRetry={() => void query.refetch()} /> : null}
    </li>
  );
}
