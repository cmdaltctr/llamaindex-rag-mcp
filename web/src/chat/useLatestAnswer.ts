import { useCallback, useMemo, useState } from "react";
import type { AnswerResult } from "../api/documents";
import type { Turn } from "./useChatSession";

export interface LatestAnswer {
  collection: string;
  result: AnswerResult;
}

/**
 * The newest usable answer of the open chat, for the Citations and Evidence
 * tabs. A reopened chat supplies saved answers. A new answer is reported by its
 * turn through `record`. An error result never counts, so a failed retry leaves
 * the last good answer in view.
 */
export function useLatestAnswer(turns: Turn[], session: number) {
  const [live, setLive] = useState<Record<string, AnswerResult>>({});
  const keyOf = (turn: Turn) => `${session}-${turn.id}`;

  const record = useCallback((turn: Turn, result: AnswerResult) => setLive((current) => ({ ...current, [`${session}-${turn.id}`]: result })), [session]);

  const latest = useMemo<LatestAnswer | null>(() => {
    for (let index = turns.length - 1; index >= 0; index -= 1) {
      const turn = turns[index]!;
      const result = turn.saved ?? live[keyOf(turn)];
      if (result !== undefined && result.status !== "error") return { collection: turn.collection, result };
    }
    return null;
    // keyOf only reads `session`, which is listed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turns, live, session]);

  return { latest, record };
}
