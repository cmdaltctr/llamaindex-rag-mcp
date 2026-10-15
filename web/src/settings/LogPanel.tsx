import { useLayoutEffect, useRef } from "react";
import type { LogLevel, LogRecord } from "../api/settings";
import { Badge } from "../components/ui/badge";

const BOTTOM_SLACK_PX = 8;

const LEVEL_VARIANT: Record<LogLevel, "neutral" | "info" | "warning" | "error"> = {
  debug: "neutral",
  info: "info",
  warning: "warning",
  error: "error",
  critical: "error",
};

/** "09:30:02" from an ISO time; anything else shows as the server sent it. */
function clock(time: string): string {
  return /T(\d{2}:\d{2}:\d{2})/.exec(time)?.[1] ?? time;
}

/** The text one record has in the clipboard. */
export function logLine(record: LogRecord): string {
  return `${record.time} ${record.level.toUpperCase()} ${record.logger} ${record.message}`;
}

interface LogPanelProps {
  records: readonly LogRecord[];
  /** Whether the panel is following new lines; the parent shows this as text. */
  onFollowingChange: (following: boolean) => void;
}

/**
 * The terminal-style panel. Messages render as plain text. The panel follows
 * new lines only while it sits at the bottom: scrolling up stops it, and
 * scrolling back to the bottom resumes it.
 */
export function LogPanel({ records, onFollowingChange }: LogPanelProps) {
  const ref = useRef<HTMLDivElement>(null);
  const following = useRef(true);

  useLayoutEffect(() => {
    const element = ref.current;
    if (element !== null && following.current) element.scrollTop = element.scrollHeight;
  }, [records]);

  function onScroll() {
    const element = ref.current;
    if (element === null) return;
    const atBottom = element.scrollHeight - element.scrollTop - element.clientHeight <= BOTTOM_SLACK_PX;
    if (atBottom !== following.current) {
      following.current = atBottom;
      onFollowingChange(atBottom);
    }
  }

  return (
    <div
      ref={ref}
      role="log"
      aria-label="Log records"
      tabIndex={0}
      onScroll={onScroll}
      className="max-h-[60vh] min-h-48 overflow-y-auto rounded-panel border border-border bg-muted p-3 font-mono text-code"
    >
      {records.length === 0 ? (
        <p className="text-muted-foreground">No log lines yet.</p>
      ) : (
        <ol className="flex flex-col gap-0.5">
          {records.map((record) => (
            <li key={record.seq} className="flex flex-wrap items-baseline gap-x-2 [overflow-wrap:anywhere]">
              <time dateTime={record.time} className="text-muted-foreground">
                {clock(record.time)}
              </time>
              <Badge variant={LEVEL_VARIANT[record.level]}>{record.level}</Badge>
              <span className="text-muted-foreground">{record.logger}</span>
              <span className="min-w-0 whitespace-pre-wrap">{record.message}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
