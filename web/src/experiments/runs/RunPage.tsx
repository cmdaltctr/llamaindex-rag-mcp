import { useQuery } from "@tanstack/react-query";
import { useApi } from "../../api/ApiProvider";
import { ApiError } from "../../api/client";
import { runQuery } from "../../api/queries";
import { ACTIVE_RUN_STATUSES, type RunDetailRecord } from "../../api/runs";
import { ErrorNotice } from "../../components/ErrorNotice";
import { NotFound } from "../../components/NotFound";
import { PageHeader } from "../../components/PageHeader";
import { formatRoute } from "../../lib/routes";
import { useRunMonitor } from "../../runs/useRunMonitor";
import { RunActions } from "./RunActions";
import { RunDetail } from "./RunDetail";

const BACK = formatRoute({ area: "experiments", runId: null });

/** A run the server does not return, or an identifier it refuses as unsafe. */
function isMissing(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || error.kind === "invalid-path");
}

function originText(run: RunDetailRecord): string {
  if (run.origin === "retry") return `Retry of run ${run.source_run_id ?? "unknown"}`;
  if (run.origin === "repeat") return "Explicit repeat of a saved revision";
  return "Submitted from a saved revision";
}

/**
 * The detail of one run at `#/experiments/runs/<run-id>`. One heading stays
 * in place while the run loads, so focus is not lost. A run the server does
 * not know shows a way back.
 */
export function RunPage({ runId }: { runId: string }) {
  const query = useQuery(runQuery(useApi(), runId));
  const record = query.data;
  const monitor = useRunMonitor(record !== undefined && ACTIVE_RUN_STATUSES.has(record.status) ? runId : null);
  const status = monitor.view.runStatus ?? record?.status ?? "";

  return (
    <section>
      <PageHeader title={`Run ${runId}`} summary={record ? originText(record) : undefined} actions={record ? <RunActions run={record} status={status} /> : undefined} />
      {record !== undefined ? (
        <RunDetail key={runId} run={record} monitor={monitor} status={status} />
      ) : query.isError ? (
        isMissing(query.error) ? (
          <NotFound what="run" name={runId} backHref={BACK} backLabel="Back to Experiments" />
        ) : (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        )
      ) : (
        <p role="status" className="text-meta text-muted-foreground">
          Loading the run.
        </p>
      )}
    </section>
  );
}
