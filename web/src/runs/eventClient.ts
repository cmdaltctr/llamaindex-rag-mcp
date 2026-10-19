/**
 * Follows the events of one run.
 *
 * Server-sent events come first. The browser reconnects by itself and sends
 * `Last-Event-ID`; a fresh stream resumes with `?after=`. Every event is
 * delivered once, in sequence order: a repeated or older sequence is dropped.
 * When the stream is refused, keeps failing, or `EventSource` is missing,
 * the client polls the JSON events route from the last delivered sequence.
 * After every reconnect (the stream opens again after an error, the client
 * switches to polling, or polling recovers after a failure) it re-reads the
 * authoritative run record and passes it to `onRefresh`.
 * It stops on `run.end`, on a complete polling page, or on `close()`.
 * Closing only stops monitoring; it never cancels the run.
 */
import { ApiError, type ApiClient } from "../api/client";
import { eventStreamPath, getRunRecord, listRunEvents, MAX_EVENT_PAGE, type RunDetailRecord, type RunEventRecord } from "../api/runs";

export type MonitorMode = "connecting" | "streaming" | "reconnecting" | "polling" | "ended" | "closed";

export interface EventSourceLike {
  readyState: number;
  onopen: ((event: Event) => void) | null;
  onerror: ((event: Event) => void) | null;
  addEventListener(type: string, listener: (event: MessageEvent) => void): void;
  close(): void;
}

export type EventSourceFactory = (url: string) => EventSourceLike;

export interface FollowOptions {
  runId: string;
  afterSequence?: number;
  onEvent: (event: RunEventRecord) => void;
  onMode?: (mode: MonitorMode) => void;
  /** `status` is null when the server closed before the run ended. */
  onEnd?: (info: { status: string | null }) => void;
  onError?: (error: unknown) => void;
  /** Receives the run record read again after each reconnect. The first connection reads nothing. */
  onRefresh?: (run: RunDetailRecord) => void;
  /** `undefined` uses the browser `EventSource`; `null` means none is available. */
  eventSource?: EventSourceFactory | null;
  api: ApiClient;
  pollIntervalMs?: number;
  schedule?: (fn: () => void, ms: number) => () => void;
  maxStreamErrors?: number;
}

/** Event names the server writes on `event:` lines (`EventKind` plus the status event). */
export const STREAM_EVENT_KINDS = [
  "run.status",
  "run_admitted",
  "run_started",
  "unit_started",
  "unit_completed",
  "unit_failed",
  "unit_cancelled",
  "node_queued",
  "node_started",
  "node_progress",
  "node_completed",
  "node_failed",
  "node_skipped",
  "node_bypassed",
  "node_fallback",
  "node_cancelled",
  "effect_committed",
  "run_cancelling",
  "run_cancelled",
  "run_completed",
  "run_failed",
] as const;

const CLOSED = 2;
const STOP_STATUSES = new Set([401, 403, 404]);

function browserEventSource(): EventSourceFactory | null {
  return typeof EventSource === "function" ? (url) => new EventSource(url) : null;
}

function defaultSchedule(fn: () => void, ms: number): () => void {
  const timer = setTimeout(fn, ms);
  return () => clearTimeout(timer);
}

function endStatus(message: MessageEvent): string | null {
  try {
    const data = JSON.parse(String(message.data)) as { status?: unknown };
    return typeof data.status === "string" ? data.status : null;
  } catch {
    return null;
  }
}

function parseRecord(message: MessageEvent): RunEventRecord | null {
  try {
    const record = JSON.parse(String(message.data)) as RunEventRecord;
    return typeof record?.sequence === "number" ? record : null;
  } catch {
    return null;
  }
}

export function followRunEvents(options: FollowOptions): { close: () => void } {
  const factory = options.eventSource === undefined ? browserEventSource() : options.eventSource;
  const schedule = options.schedule ?? defaultSchedule;
  const interval = options.pollIntervalMs ?? 1000;
  const maxErrors = options.maxStreamErrors ?? 3;
  let last = options.afterSequence ?? 0;
  let stopped = false;
  let source: EventSourceLike | null = null;
  let cancelTimer: (() => void) | null = null;

  const setMode = (mode: MonitorMode) => options.onMode?.(mode);

  function deliver(record: RunEventRecord) {
    if (stopped || record.sequence <= last) return;
    last = record.sequence;
    options.onEvent(record);
  }

  function refresh() {
    if (stopped || !options.onRefresh) return;
    getRunRecord(options.api, options.runId).then(
      (run) => {
        if (!stopped) options.onRefresh?.(run);
      },
      (error: unknown) => {
        if (!stopped) options.onError?.(error);
      },
    );
  }

  function stop(mode: MonitorMode) {
    stopped = true;
    source?.close();
    cancelTimer?.();
    setMode(mode);
  }

  async function poll(failures: number) {
    if (stopped) return;
    try {
      const page = await listRunEvents(options.api, options.runId, last);
      if (failures > 0) refresh();
      for (const record of page.events) deliver(record);
      if (stopped) return;
      if (page.complete) {
        stop("ended");
        options.onEnd?.({ status: page.run_status });
        return;
      }
      cancelTimer = schedule(() => void poll(0), page.events.length >= MAX_EVENT_PAGE ? 0 : interval);
    } catch (error) {
      if (stopped) return;
      options.onError?.(error);
      if (error instanceof ApiError && error.status !== null && STOP_STATUSES.has(error.status)) return stop("closed");
      cancelTimer = schedule(() => void poll(failures + 1), interval * Math.min(failures + 1, 5));
    }
  }

  function startPolling() {
    source?.close();
    source = null;
    setMode("polling");
    void poll(0);
  }

  function switchToPolling() {
    startPolling();
    refresh();
  }

  function startStream(open: EventSourceFactory) {
    setMode("connecting");
    const stream = open(eventStreamPath(options.runId, last));
    source = stream;
    let errors = 0;
    let dropped = false;
    stream.onopen = () => {
      errors = 0;
      setMode("streaming");
      if (dropped) refresh();
      dropped = false;
    };
    stream.onerror = () => {
      if (stopped) return;
      errors += 1;
      dropped = true;
      if (stream.readyState === CLOSED || errors >= maxErrors) switchToPolling();
      else setMode("reconnecting");
    };
    const onFrame = (message: MessageEvent) => {
      errors = 0;
      const record = parseRecord(message);
      if (record) deliver(record);
    };
    for (const kind of STREAM_EVENT_KINDS) stream.addEventListener(kind, onFrame);
    stream.addEventListener("run.end", (message) => {
      stop("ended");
      options.onEnd?.({ status: endStatus(message) });
    });
    stream.addEventListener("server.closing", () => {
      stop("closed");
      options.onEnd?.({ status: null });
    });
  }

  if (factory) startStream(factory);
  else startPolling();

  return {
    close: () => {
      if (!stopped) stop("closed");
    },
  };
}
