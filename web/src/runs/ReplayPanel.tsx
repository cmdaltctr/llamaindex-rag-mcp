import { useEffect, useMemo, useState } from "react";
import type { FetchLike } from "../api/client";
import { listRunEvents, type RunEventRecord } from "../api/runs";
import { NodeRunBadge } from "./NodeRunBadge";
import { foldEvents } from "./runState";

/** Upper bound on events loaded for one replay (each page holds at most 500). */
const MAX_REPLAY_EVENTS = 5000;

async function loadAll(runId: string, fetchImpl?: FetchLike): Promise<{ events: RunEventRecord[]; capped: boolean }> {
  const events: RunEventRecord[] = [];
  let after = 0;
  while (events.length < MAX_REPLAY_EVENTS) {
    const page = await listRunEvents(runId, after, { fetchImpl });
    const fresh = page.events.filter((event) => event.sequence > after);
    events.push(...fresh);
    if (fresh.length === 0 || page.complete) return { events, capped: false };
    after = fresh.at(-1)!.sequence;
  }
  return { events, capped: true };
}

interface ReplayPanelProps {
  runId: string;
  nodeIds: string[];
  fetchImpl?: FetchLike;
}

/**
 * Historical playback of a finished run. It steps through recorded events
 * on request only; it never executes operations and never claims to be live.
 */
export function ReplayPanel({ runId, nodeIds, fetchImpl }: ReplayPanelProps) {
  const [loaded, setLoaded] = useState<{ events: RunEventRecord[]; capped: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState(0);

  useEffect(() => {
    let live = true;
    loadAll(runId, fetchImpl).then(
      (result) => {
        if (!live) return;
        setLoaded(result);
        setStep(result.events.length);
      },
      (failure: unknown) => live && setError(failure instanceof Error ? failure.message : String(failure)),
    );
    return () => {
      live = false;
    };
  }, [runId, fetchImpl]);

  const events = useMemo(() => loaded?.events ?? [], [loaded]);
  const view = useMemo(() => foldEvents(events.slice(0, step)), [events, step]);
  const current = step > 0 ? events[step - 1] : undefined;
  const ids = [...new Set([...nodeIds, ...Object.keys(view.nodes)])];

  return (
    <section className="run-section" aria-label="Replay">
      <h3 className="text-subsection-title replay__label">Replay</h3>
      <p className="text-meta">Replay of recorded events. Nothing runs again.</p>
      {error && <p className="text-meta">{`Could not load the recorded events: ${error}`}</p>}
      {!loaded && !error && <p className="text-meta">Loading recorded events.</p>}
      {loaded && events.length === 0 && <p className="text-meta">This run recorded no events.</p>}
      {loaded && events.length > 0 && (
        <>
          {loaded.capped && <p className="text-meta">{`Only the first ${MAX_REPLAY_EVENTS} events are loaded.`}</p>}
          <div className="run-actions">
            <button type="button" className="button button--small" disabled={step <= 1} onClick={() => setStep(1)}>
              Go to first event
            </button>
            <button type="button" className="button button--small" disabled={step <= 1} onClick={() => setStep(step - 1)}>
              Previous event
            </button>
            <button type="button" className="button button--small" disabled={step >= events.length} onClick={() => setStep(step + 1)}>
              Next event
            </button>
            <button type="button" className="button button--small" disabled={step >= events.length} onClick={() => setStep(events.length)}>
              Go to last event
            </button>
          </div>
          <p className="text-meta" aria-live="polite">
            {`Event ${step} of ${events.length}`}
            {current ? `: ${current.kind}${current.node_id ? ` (${current.node_id})` : ""}, recorded ${current.created_at}` : ""}
          </p>
          <ul className="replay-nodes" aria-label="Node states at this event">
            {ids.map((id) => (
              <li key={id}>
                <code>{id}</code>
                <NodeRunBadge state={view.nodes[id]} />
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
