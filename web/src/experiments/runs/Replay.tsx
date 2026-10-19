import { useQuery } from "@tanstack/react-query";
import { ChevronFirst, ChevronLast, StepBack, StepForward } from "lucide-react";
import { useMemo, useState } from "react";
import { useApi } from "../../api/ApiProvider";
import { queryKeys } from "../../api/queries";
import { listRunEvents, type RunEventRecord } from "../../api/runs";
import { ErrorNotice } from "../../components/ErrorNotice";
import { Button } from "../../components/ui/button";
import { foldEvents } from "../../runs/runState";
import { NodeRunStatus } from "../../studio/NodeRunStatus";
import { Panel } from "../Panel";
import { OutputCut } from "./OutputViewer";

/** Upper bound on events loaded for one replay (each page holds at most 500). */
const MAX_REPLAY_EVENTS = 5000;

interface Loaded {
  events: RunEventRecord[];
  capped: boolean;
}

async function loadAll(api: ReturnType<typeof useApi>, runId: string, signal: AbortSignal): Promise<Loaded> {
  const events: RunEventRecord[] = [];
  let after = 0;
  while (events.length < MAX_REPLAY_EVENTS) {
    const page = await listRunEvents(api, runId, after, { signal });
    const fresh = page.events.filter((event) => event.sequence > after);
    events.push(...fresh);
    if (fresh.length === 0 || page.complete) return { events, capped: false };
    after = fresh.at(-1)!.sequence;
  }
  return { events, capped: true };
}

/** The step the user chose, or the last event until they choose one. */
function Playback({ runId, nodeIds, loaded }: { runId: string; nodeIds: string[]; loaded: Loaded }) {
  const { events, capped } = loaded;
  const [chosen, setChosen] = useState<number | null>(null);
  const step = Math.min(chosen ?? events.length, events.length);
  const view = useMemo(() => foldEvents(events.slice(0, step)), [events, step]);
  const current = step > 0 ? events[step - 1] : undefined;
  const ids = [...new Set([...nodeIds, ...Object.keys(view.nodes)])];

  return (
    <>
      {capped && <p className="text-meta text-muted-foreground">{`Only the first ${MAX_REPLAY_EVENTS} events are loaded.`}</p>}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" disabled={step <= 1} onClick={() => setChosen(1)}>
          <ChevronFirst aria-hidden="true" />
          Go to first event
        </Button>
        <Button variant="outline" size="sm" disabled={step <= 1} onClick={() => setChosen(step - 1)}>
          <StepBack aria-hidden="true" />
          Previous event
        </Button>
        <Button variant="outline" size="sm" disabled={step >= events.length} onClick={() => setChosen(step + 1)}>
          <StepForward aria-hidden="true" />
          Next event
        </Button>
        <Button variant="outline" size="sm" disabled={step >= events.length} onClick={() => setChosen(events.length)}>
          <ChevronLast aria-hidden="true" />
          Go to last event
        </Button>
      </div>
      <p className="text-meta text-muted-foreground" aria-live="polite">
        {`Event ${step} of ${events.length}`}
        {current ? `: ${current.kind}${current.node_id ? ` (${current.node_id})` : ""}, recorded ${current.created_at}` : ""}
      </p>
      {current && <OutputCut runId={runId} name={`event-${current.sequence}-summary`} value={current.summary} />}
      <ul aria-label="Node states at this event" className="flex flex-col gap-1">
        {ids.map((id) => (
          <li key={id} className="flex flex-wrap items-center gap-x-3">
            <code className="font-mono text-code">{id}</code>
            <NodeRunStatus state={view.nodes[id]} />
          </li>
        ))}
      </ul>
    </>
  );
}

/**
 * Historical playback of a finished run. It steps through recorded events
 * on request only; it never executes operations and never claims to be live.
 */
export function Replay({ runId, nodeIds }: { runId: string; nodeIds: string[] }) {
  const api = useApi();
  const events = useQuery({ queryKey: queryKeys.runEvents(runId), queryFn: ({ signal }) => loadAll(api, runId, signal) });
  return (
    <Panel title="Replay" level={3} description="Replay of recorded events. Nothing runs again.">
      {events.isError && <ErrorNotice error={events.error} onRetry={() => void events.refetch()} />}
      {events.isPending && (
        <p role="status" className="text-meta text-muted-foreground">
          Loading recorded events.
        </p>
      )}
      {events.data && events.data.events.length === 0 && <p className="text-meta text-muted-foreground">This run recorded no events.</p>}
      {events.data && events.data.events.length > 0 && <Playback runId={runId} nodeIds={nodeIds} loaded={events.data} />}
    </Panel>
  );
}
