import type { Job } from "../api/documents";

export interface JobOutcome {
  text: string;
  variant: "neutral" | "info" | "success" | "warning" | "error";
  detail: string | null;
}

const LOG_HINT = "See the server log in Settings for the reason.";

const STAGE_HINT: Record<string, string> = {
  embedding: "The embedding step failed. Check the embedding model, then try again.",
};

function failedFiles(result: Job["result"]): { failed: number; total: number; stage: string | null } | null {
  const details = result?.file_details;
  if (!Array.isArray(details)) return null;
  const failed = details.filter((item) => typeof item === "object" && item !== null && (item as { status?: unknown }).status === "failed");
  const stages = new Set(failed.map((item) => (item as { failure_stage?: unknown }).failure_stage).filter((stage): stage is string => typeof stage === "string"));
  return { failed: failed.length, total: details.length, stage: stages.size === 1 ? [...stages][0]! : null };
}

const files = (count: number) => (count === 1 ? "file" : "files");

/**
 * What to show for an ingest job. A job the server marks `completed` can still
 * carry a result in which files failed to index, so the result decides the
 * wording. Only counts and fixed hints are returned: the per-file messages and
 * the job error hold local paths and exception text, which stay out of the page.
 */
export function jobOutcome(job: Job): JobOutcome {
  if (job.status === "queued") return { text: "Queued", variant: "neutral", detail: null };
  if (job.status === "running") return { text: "Running", variant: "info", detail: null };
  if (job.status === "failed") return { text: "Failed", variant: "error", detail: `The ingest stopped before it finished. ${LOG_HINT}` };

  const counts = failedFiles(job.result);
  if (job.result?.status === "error") {
    if (counts === null || counts.failed === 0) return { text: "Nothing indexed", variant: "error", detail: `The ingest did not finish. ${LOG_HINT}` };
    const hint = counts.stage === null ? LOG_HINT : (STAGE_HINT[counts.stage] ?? LOG_HINT);
    return { text: "Nothing indexed", variant: "error", detail: `${counts.failed} of ${counts.total} ${files(counts.total)} could not be indexed. ${hint}` };
  }
  if (counts !== null && counts.failed > 0) {
    return { text: "Completed with errors", variant: "warning", detail: `${counts.failed} of ${counts.total} ${files(counts.total)} could not be indexed. ${LOG_HINT}` };
  }
  return { text: "Completed", variant: "success", detail: null };
}
