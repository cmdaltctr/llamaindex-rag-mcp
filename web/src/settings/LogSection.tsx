import { Pause, Play } from "lucide-react";
import { useState } from "react";
import type { LogLevel } from "../api/settings";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { plural } from "../lib/labels";
import { CopyButton } from "./CopyButton";
import { logLine, LogPanel } from "./LogPanel";
import { LOG_POLL_MS, useServerLog, type LogMode } from "./useServerLog";

const RANK: Record<LogLevel, number> = { debug: 0, info: 1, warning: 2, error: 3, critical: 4 };

const LEVEL_CHIPS = [
  { label: "All", rank: 0 },
  { label: "Info", rank: 1 },
  { label: "Warning", rank: 2 },
  { label: "Error", rank: 3 },
] as const;

const MODE_TEXT: Record<LogMode, string> = {
  loading: "Loading the log.",
  streaming: "Live.",
  reconnecting: "Reconnecting to the server.",
  polling: `Checking for new lines every ${LOG_POLL_MS / 1000} seconds.`,
  ended: "The server is shutting down. The log stopped following.",
  error: "",
};

/** The server's recent log, redacted by the server, with a level filter, Pause and Copy. */
export function LogSection() {
  const { records, mode, error, retry } = useServerLog();
  const [minimum, setMinimum] = useState(0);
  const [pausedAt, setPausedAt] = useState<number | null>(null);
  const [following, setFollowing] = useState(true);

  const newest = records.at(-1)?.seq ?? 0;
  const shown = records.filter((record) => RANK[record.level] >= minimum && (pausedAt === null || record.seq <= pausedAt));
  const waiting = pausedAt === null ? 0 : records.filter((record) => record.seq > pausedAt).length;

  return (
    <section aria-labelledby="settings-log" className="flex flex-col gap-3">
      <h2 id="settings-log" className="text-section-title font-semibold">
        Server log
      </h2>
      <p className="text-meta text-muted-foreground">The last 1,000 lines, kept in memory only. The server removes keys and tokens before it stores a line.</p>
      {mode === "error" ? (
        <ErrorNotice error={error} onRetry={retry} />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <div role="group" aria-label="Minimum level" className="flex flex-wrap gap-2">
              {LEVEL_CHIPS.map(({ label, rank }) => (
                <Button key={label} variant="chip" size="sm" aria-pressed={minimum === rank} onClick={() => setMinimum(rank)}>
                  {label}
                </Button>
              ))}
            </div>
            <Button variant="outline" size="sm" aria-pressed={pausedAt !== null} onClick={() => setPausedAt(pausedAt === null ? newest : null)}>
              {pausedAt === null ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
              {pausedAt === null ? "Pause" : "Resume"}
            </Button>
            <CopyButton text={shown.map(logLine).join("\n")} what="visible log lines" />
          </div>
          <LogPanel records={shown} onFollowingChange={setFollowing} />
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-meta text-muted-foreground">
            <span>{MODE_TEXT[mode]}</span>
            <span>{following ? "Following new lines." : "Not following. Scroll to the bottom to follow new lines."}</span>
            {waiting > 0 ? <span>{plural(waiting, "new line")} while paused.</span> : null}
          </div>
        </>
      )}
    </section>
  );
}
