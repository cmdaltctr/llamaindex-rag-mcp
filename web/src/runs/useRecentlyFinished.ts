import { useEffect, useMemo, useRef, useState } from "react";
import { finishedNodes, type NodeRunState } from "./runState";

/** How long the edge into a step that just finished keeps its animation. */
export const FINISH_HOLD_MS = 1500;

interface Held {
  /** The states that the last render compared against. */
  seen: Readonly<Record<string, NodeRunState>>;
  /** Step id to the batch that finished it. Steps in one batch leave together. */
  held: Readonly<Record<string, number>>;
  batch: number;
}

/**
 * The steps that finished with success a moment ago, for the edge animation.
 * Only a run that was live when watching began counts: a finished run that is
 * replayed event by event must not flash its edges.
 */
export function useRecentlyFinished(states: Readonly<Record<string, NodeRunState>>, live: boolean | null): ReadonlySet<string> {
  const [state, setState] = useState<Held>({ seen: states, held: {}, batch: 0 });
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  // Compared during render, so the new states and the held set land in one commit.
  if (state.seen !== states) {
    const done = live === true ? finishedNodes(state.seen, states) : [];
    const batch = done.length > 0 ? state.batch + 1 : state.batch;
    setState({ seen: states, held: { ...state.held, ...Object.fromEntries(done.map((id) => [id, batch])) }, batch });
  }

  useEffect(() => {
    for (const batch of new Set(Object.values(state.held))) {
      if (timers.current.has(batch)) continue;
      timers.current.set(
        batch,
        setTimeout(() => {
          timers.current.delete(batch);
          setState((current) => ({ ...current, held: Object.fromEntries(Object.entries(current.held).filter(([, member]) => member !== batch)) }));
        }, FINISH_HOLD_MS),
      );
    }
  }, [state.held]);

  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const timer of pending.values()) clearTimeout(timer);
      pending.clear();
    };
  }, []);

  return useMemo(() => new Set(Object.keys(state.held)), [state.held]);
}
