import { RotateCcw, Square } from "lucide-react";
import { useCancelRun } from "../../api/mutations";
import { ACTIVE_RUN_STATUSES, RETRYABLE_RUN_STATUSES, type RunDetailRecord } from "../../api/runs";
import { ErrorNotice } from "../../components/ErrorNotice";
import { Button } from "../../components/ui/button";
import { useRoute } from "../../lib/RouteProvider";
import { formatRoute } from "../../lib/routes";
import { RunStatusBadge } from "../../studio/RunStatusBadge";
import { useRetryRun } from "../mutations";

/** The run status, a way back, and the one action the status allows: cancel an active run or retry an ended one. */
export function RunActions({ run, status }: { run: RunDetailRecord; status: string }) {
  const { navigate } = useRoute();
  const cancel = useCancelRun();
  const retry = useRetryRun();

  async function retryRun() {
    try {
      const retried = await retry.mutateAsync(run.run_id);
      navigate({ area: "experiments", runId: retried.run_id });
    } catch {
      // The mutation holds the error, which renders below.
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <RunStatusBadge status={status} />
        <Button asChild variant="outline">
          <a href={formatRoute({ area: "experiments", runId: null })}>Back to Experiments</a>
        </Button>
        {ACTIVE_RUN_STATUSES.has(run.status) && (
          <Button variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate(run.run_id)}>
            <Square aria-hidden="true" />
            Cancel run
          </Button>
        )}
        {RETRYABLE_RUN_STATUSES.has(run.status) && (
          <Button disabled={retry.isPending} onClick={() => void retryRun()}>
            <RotateCcw aria-hidden="true" />
            Retry as a new run
          </Button>
        )}
      </div>
      {cancel.isError && <ErrorNotice error={cancel.error} />}
      {retry.isError && <ErrorNotice error={retry.error} />}
    </div>
  );
}
