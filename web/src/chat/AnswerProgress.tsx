import { Check, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { AnswerStage } from "../api/answerStream";

const STAGE_LABELS: Record<AnswerStage, string> = {
  searching: "Searching",
  writing: "Writing the answer",
  citing: "Checking citations",
  verifying: "Verifying claims",
};

const WAITING = "Waiting for the answer.";

/** Seconds since the component mounted, which is when the question was sent. */
function useElapsedSeconds(): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const start = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);
  return seconds;
}

/**
 * The stages of a running answer. Finished stages keep a tick; the current
 * one is the only polite live region, so a screen reader hears each stage
 * once. A stage that has not started has no row, so the list never needs to
 * know whether verification runs. The counter stays outside the live region.
 */
export function AnswerProgress({ stages }: { stages: readonly AnswerStage[] }) {
  const seconds = useElapsedSeconds();
  const done = stages.slice(0, -1);
  const current = stages.at(-1);
  return (
    <div className="flex flex-col gap-1">
      <ul aria-label="Answer progress" className="flex flex-col gap-1 text-meta">
        {done.map((stage) => (
          <li key={stage} className="flex min-w-0 items-center gap-2 text-muted-foreground">
            <Check aria-hidden="true" className="size-4 shrink-0" />
            <span>{STAGE_LABELS[stage]}</span>
          </li>
        ))}
        <li key="current" className="flex min-w-0 items-center gap-2 text-foreground">
          {current === undefined ? null : <Loader2 aria-hidden="true" className="size-4 shrink-0 motion-safe:animate-spin" />}
          <span role="status" aria-live="polite" className={current === undefined ? "text-muted-foreground" : undefined}>
            {current === undefined ? WAITING : STAGE_LABELS[current]}
          </span>
        </li>
      </ul>
      <p aria-hidden="true" className="text-meta text-muted-foreground tabular-nums">
        {seconds} s
      </p>
    </div>
  );
}
