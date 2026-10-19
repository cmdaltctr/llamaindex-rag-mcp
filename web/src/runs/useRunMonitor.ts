import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useApi } from "../api/ApiProvider";
import { queryKeys } from "../api/queries";
import { ACTIVE_RUN_STATUSES, getRunRecord } from "../api/runs";
import { followRunEvents, type EventSourceFactory, type MonitorMode } from "./eventClient";
import { applyEvent, EMPTY_RUN_VIEW, reconcileRun, type RunView } from "./runState";

export interface MonitorOptions {
  eventSource?: EventSourceFactory | null;
  pollIntervalMs?: number;
}

export interface RunMonitor {
  view: RunView;
  mode: MonitorMode | null;
  /** True when the run was active when monitoring began. A finished run is never shown as live. */
  live: boolean | null;
  /** Status read from the server after the stream ended (authoritative refresh). */
  refreshedStatus: string | null;
  /** The last monitoring failure, or null. Render it through `describeError`; its raw text never reaches the page. */
  error: unknown;
}

const IDLE: RunMonitor = { view: EMPTY_RUN_VIEW, mode: null, live: null, refreshedStatus: null, error: null };

/**
 * Follows the events of one run and folds them into a view. Unmounting or a
 * new run id only detaches monitoring; the run itself continues.
 */
export function useRunMonitor(runId: string | null, options: MonitorOptions = {}): RunMonitor {
  const { eventSource, pollIntervalMs } = options;
  const api = useApi();
  const queryClient = useQueryClient();
  const [state, setState] = useState<RunMonitor & { runId: string | null }>({ ...IDLE, runId });

  if (state.runId !== runId) setState({ ...IDLE, runId });

  useEffect(() => {
    if (runId === null) return;
    let detached = false;
    let follower: { close: () => void } | null = null;
    const update = (change: (current: RunMonitor) => Partial<RunMonitor>) =>
      setState((current) => (detached || current.runId !== runId ? current : { ...current, ...change(current) }));

    getRunRecord(api, runId).then(
      (run) => {
        if (detached) return;
        update(() => ({ live: ACTIVE_RUN_STATUSES.has(run.status) }));
        follower = followRunEvents({
          api,
          runId,
          eventSource,
          pollIntervalMs,
          onEvent: (event) => update((current) => ({ view: applyEvent(current.view, event), error: null })),
          onMode: (mode) => update(() => ({ mode })),
          onRefresh: (latest) => update((current) => ({ view: reconcileRun(current.view, latest) })),
          onError: (error) => update(() => ({ error })),
          onEnd: ({ status }) => {
            // A terminal status makes the cached run and every run list stale.
            if (status !== null) void queryClient.invalidateQueries({ queryKey: queryKeys.allRuns() });
            getRunRecord(api, runId).then(
              (latest) => update(() => ({ refreshedStatus: latest.status })),
              (error: unknown) => update(() => ({ error })),
            );
          },
        });
      },
      (error: unknown) => update(() => ({ error })),
    );
    return () => {
      detached = true;
      follower?.close();
    };
  }, [runId, api, queryClient, eventSource, pollIntervalMs]);

  return state.runId === runId ? state : { ...IDLE };
}
