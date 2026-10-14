import { useEffect, useEffectEvent, useState } from "react";
import type { FetchLike } from "../../api/client";
import { getJob, type Job } from "../../api/documents";
import { messageOf } from "../shared/labels";

export interface TrackedJob {
  job: Job;
  label: string;
}

interface JobListProps {
  jobs: TrackedJob[];
  pollMs: number;
  fetchImpl?: FetchLike;
  onFinished: () => void;
}

/** Ingestion jobs this page started, polled until they finish. */
export function JobList({ jobs, pollMs, fetchImpl, onFinished }: JobListProps) {
  if (jobs.length === 0) return null;
  return (
    <ul className="job-list" aria-label="Jobs">
      {jobs.map((tracked) => (
        <JobItem key={tracked.job.job_id} tracked={tracked} pollMs={pollMs} fetchImpl={fetchImpl} onFinished={onFinished} />
      ))}
    </ul>
  );
}

function isFinished(job: Job): boolean {
  return job.status === "completed" || job.status === "failed";
}

function statusText(job: Job): string {
  if (job.status === "failed") return `Failed: ${job.error ?? "no reason given"}`;
  return { queued: "Queued", running: "Running", completed: "Completed" }[job.status];
}

function JobItem({ tracked, pollMs, fetchImpl, onFinished }: { tracked: TrackedJob; pollMs: number; fetchImpl?: FetchLike; onFinished: () => void }) {
  const [job, setJob] = useState(tracked.job);
  const [pollError, setPollError] = useState<string | null>(null);
  const finished = useEffectEvent(onFinished);
  const done = isFinished(job);

  useEffect(() => {
    if (done) {
      finished();
      return;
    }
    const timer = window.setTimeout(() => {
      getJob(job.job_id, { fetchImpl }).then(
        (next) => {
          setPollError(null);
          setJob(next);
        },
        // Keep polling after a transient failure, but say so.
        (error: unknown) => {
          setPollError(messageOf(error));
          setJob((current) => ({ ...current }));
        },
      );
    }, pollMs);
    return () => window.clearTimeout(timer);
  }, [job, done, pollMs, fetchImpl]);

  return (
    <li className="job-list__item" data-status={job.status}>
      <span className="type-code" dir="ltr">
        {tracked.label}
      </span>
      <span role="status">{statusText(job)}</span>
      {pollError !== null ? <span className="type-meta">Could not check the job: {pollError}</span> : null}
    </li>
  );
}
