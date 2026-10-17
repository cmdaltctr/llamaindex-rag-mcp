import { useQuery } from "@tanstack/react-query";
import { Play, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useApi } from "../../api/ApiProvider";
import type { ExperimentList } from "../../api/experiments";
import { runsQuery } from "../../api/queries";
import { RUN_STATUSES, type RunDetailRecord } from "../../api/runs";
import { EmptyState } from "../../components/EmptyState";
import { ErrorNotice } from "../../components/ErrorNotice";
import { Button } from "../../components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import { formatRoute } from "../../lib/routes";
import { RunStatusBadge } from "../../studio/RunStatusBadge";
import { contextLabel } from "../labels";
import { Panel } from "../Panel";

const LIST_LIMIT = 100;

interface ExperimentResource {
  context_id?: unknown;
  /** Backend provenance recorded at admission; it holds the index identity. */
  backend?: { index_identity?: unknown } | null;
}

function experimentOf(run: RunDetailRecord): ExperimentResource | null {
  const value = run.resources?.experiment;
  return typeof value === "object" && value !== null ? (value as ExperimentResource) : null;
}

function RunTable({ runs, names }: { runs: RunDetailRecord[]; names: Record<string, string> }) {
  return (
    <Table aria-label="Runs">
      <TableHeader>
        <TableRow>
          <TableHead scope="col">Run</TableHead>
          <TableHead scope="col">Status</TableHead>
          <TableHead scope="col">Pipeline</TableHead>
          <TableHead scope="col">Created</TableHead>
          <TableHead scope="col">Experiment context</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {runs.map((run) => {
          const experiment = experimentOf(run);
          const contextId = typeof experiment?.context_id === "string" ? experiment.context_id : null;
          const identity = typeof experiment?.backend?.index_identity === "string" ? experiment.backend.index_identity : null;
          return (
            <TableRow key={run.run_id}>
              <TableCell>
                <a href={formatRoute({ area: "experiments", runId: run.run_id })} className="font-mono text-code text-primary-label underline underline-offset-4">
                  {run.run_id}
                </a>
              </TableCell>
              <TableCell>
                <RunStatusBadge status={run.status} />
              </TableCell>
              <TableCell dir="ltr" className="font-mono text-code">
                {run.pipeline_id}
              </TableCell>
              <TableCell>{run.created_at}</TableCell>
              <TableCell>
                {contextId === null ? (
                  <span className="text-muted-foreground">None</span>
                ) : (
                  <>
                    {names[contextId] ?? contextId}
                    {identity !== null && <span dir="ltr" className="block font-mono text-code text-muted-foreground">{identity}</span>}
                  </>
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

/** Recorded pipeline runs with a status filter and refresh. Each run opens its own address. */
export function RunsSection({ experiments }: { experiments: ExperimentList | undefined }) {
  const api = useApi();
  const [status, setStatus] = useState("");
  const runs = useQuery(runsQuery(api, { statuses: status ? [status] : [], limit: LIST_LIMIT }));
  const names = Object.fromEntries((experiments?.experiments ?? []).map(({ experiment }) => [experiment.context_id, contextLabel(experiment)]));

  return (
    <Panel title="Pipeline runs" description="Each pipeline run is recorded with its saved revision and events. Open one to see its snapshot, node outcomes and evidence.">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Filter by status" className="flex flex-wrap gap-2">
          {["", ...RUN_STATUSES].map((value) => (
            <Button key={value || "all"} variant="chip" size="sm" aria-pressed={status === value} onClick={() => setStatus(value)}>
              {value || "All statuses"}
            </Button>
          ))}
        </div>
        <Button variant="outline" size="sm" disabled={runs.isFetching} onClick={() => void runs.refetch()}>
          <RefreshCw aria-hidden="true" />
          Refresh list
        </Button>
      </div>
      {runs.isError && <ErrorNotice error={runs.error} onRetry={() => void runs.refetch()} />}
      {runs.isPending && (
        <p role="status" className="text-meta text-muted-foreground">
          Loading runs.
        </p>
      )}
      {runs.data && runs.data.length === 0 && (
        <EmptyState
          icon={Play}
          message={status ? `No run has the status ${status}.` : "No pipeline has run yet."}
          action={
            status ? (
              <Button variant="outline" onClick={() => setStatus("")}>
                Show all statuses
              </Button>
            ) : (
              <Button asChild variant="outline">
                <a href={formatRoute({ area: "studio", profileId: null, purpose: null })}>Open Studio</a>
              </Button>
            )
          }
        />
      )}
      {runs.data && runs.data.length > 0 && <RunTable runs={runs.data} names={names} />}
    </Panel>
  );
}
