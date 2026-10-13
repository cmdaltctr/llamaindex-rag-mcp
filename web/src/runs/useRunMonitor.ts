import { useEffect, useState } from "react";
import type { FetchLike } from "../api/client";
import { ACTIVE_RUN_STATUSES, getRunRecord } from "../api/runs";
import { followRunEvents, type EventSourceFactory, type MonitorMode } from "./eventClient";
import { applyEvent, EMPTY_RUN_VIEW, type RunView } from "./runState";

export interface MonitorOptions {
  fetchImpl?: FetchLike;
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
  error: string | null;
}

const IDLE: RunMonitor = { view: EMPTY_RUN_VIEW, mode: null, live: null, refreshedStatus: null, error: null };

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Follows the events of one run and folds them into a view. Unmounting or a
 * new run id only detaches monitoring; the run itself continues.
 */
export function useRunMonitor(runId: string | null, options: MonitorOptions = {}): RunMonitor {
  const { fetchImpl, eventSource, pollIntervalMs } = options;
  const [state, setState] = useState<RunMonitor & { runId: string | null }>({ ...IDLE, runId });

  if (state.runId !== runId) setState({ ...IDLE, runId });

  useEffect(() => {
    if (runId === null) return;
    let detached = false;
    let follower: { close: () => void } | null = null;
    const update = (change: (current: RunMonitor) => Partial<RunMonitor>) =>
      setState((current) => (detached || current.runId !== runId ? current : { ...current, ...change(current) }));

    getRunRecord(runId, { fetchImpl }).then(
      (run) => {
        if (detached) return;
        update(() => ({ live: ACTIVE_RUN_STATUSES.has(run.status) }));
        follower = followRunEvents({
          runId,
          fetchImpl,
          eventSource,
          pollIntervalMs,
          onEvent: (event) => update((current) => ({ view: applyEvent(current.view, event), error: null })),
          onMode: (mode) => update(() => ({ mode })),
          onError: (text) => update(() => ({ error: text })),
          onEnd: () => {
            getRunRecord(runId, { fetchImpl }).then(
              (latest) => update(() => ({ refreshedStatus: latest.status })),
              (error: unknown) => update(() => ({ error: message(error) })),
            );
          },
        });
      },
      (error: unknown) => update(() => ({ error: message(error) })),
    );
    return () => {
      detached = true;
      follower?.close();
    };
  }, [runId, fetchImpl, eventSource, pollIntervalMs]);

  return state.runId === runId ? state : { ...IDLE };
}
