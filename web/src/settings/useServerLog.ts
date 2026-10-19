/**
 * Follows the server log. The buffered records load first. Server-sent events
 * then carry new ones; the browser reconnects by itself and sends
 * `Last-Event-ID`. When the stream is refused, or `EventSource` is missing, the
 * hook polls `GET /v1/logs?after=` instead. Records are kept in order, each
 * sequence once, and at most `MAX_LOG_RECORDS` of them (the server's own cap).
 */
import { useCallback, useEffect, useState } from "react";
import { useApi } from "../api/ApiProvider";
import { getLogs, LOG_STREAM_PATH, type LogRecord } from "../api/settings";

export const MAX_LOG_RECORDS = 1000;
export const LOG_POLL_MS = 3000;
const CLOSED = 2;

export type LogMode = "loading" | "streaming" | "reconnecting" | "polling" | "ended" | "error";

interface Options {
  pollMs?: number;
}

export function useServerLog({ pollMs = LOG_POLL_MS }: Options = {}) {
  const api = useApi();
  const [records, setRecords] = useState<LogRecord[]>([]);
  const [mode, setMode] = useState<LogMode>("loading");
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);

  const retry = useCallback(() => {
    setRecords([]);
    setError(null);
    setMode("loading");
    setAttempt((value) => value + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let lastSeq = 0;
    let source: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    function add(incoming: LogRecord[]) {
      const fresh = incoming.filter((record) => record.seq > lastSeq);
      if (fresh.length === 0) return;
      lastSeq = Math.max(lastSeq, ...fresh.map((record) => record.seq));
      setRecords((previous) => [...previous, ...fresh].slice(-MAX_LOG_RECORDS));
    }

    function poll() {
      setMode("polling");
      timer = setTimeout(async () => {
        try {
          add((await getLogs(api, lastSeq, { signal: controller.signal })).records);
        } catch {
          // A failed poll waits for the next turn; the records already shown stay.
        }
        if (!stopped) poll();
      }, pollMs);
    }

    function stream() {
      if (typeof EventSource !== "function") {
        poll();
        return;
      }
      const opened = new EventSource(`${LOG_STREAM_PATH}?after=${lastSeq}`);
      source = opened;
      opened.onopen = () => setMode("streaming");
      opened.addEventListener("log", (event) => {
        try {
          add([JSON.parse(String(event.data)) as LogRecord]);
        } catch {
          // A frame that is not a record is skipped.
        }
      });
      opened.addEventListener("server.closing", () => {
        opened.close();
        setMode("ended");
      });
      opened.onerror = () => {
        if (opened.readyState === CLOSED) {
          opened.close();
          poll();
        } else {
          setMode("reconnecting");
        }
      };
    }

    getLogs(api, 0, { signal: controller.signal }).then(
      (list) => {
        if (stopped) return;
        add(list.records);
        lastSeq = Math.max(lastSeq, list.last_seq);
        stream();
      },
      (failure: unknown) => {
        if (stopped) return;
        setError(failure);
        setMode("error");
      },
    );

    return () => {
      stopped = true;
      controller.abort();
      source?.close();
      if (timer !== null) clearTimeout(timer);
    };
  }, [api, attempt, pollMs]);

  return { records, mode, error, retry };
}
