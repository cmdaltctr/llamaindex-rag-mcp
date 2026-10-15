import { useState } from "react";
import { useCreatePipeline } from "../api/mutations";
import { useRoute } from "../lib/RouteProvider";
import type { Draft } from "./graph";
import { writeDraft } from "./storage";

/**
 * Creates a pipeline on the server from a gallery card, stores the card's
 * graph as the draft of the new id and opens `#/studio/<pipeline-id>`. The
 * server record holds the title only; the first revision comes from the canvas.
 */
export function useStartPipeline() {
  const create = useCreatePipeline();
  const { navigate } = useRoute();
  const [attempt, setAttempt] = useState<{ title: string; draft: Draft } | null>(null);

  function start(title: string, draft: Draft) {
    setAttempt({ title, draft });
    create.mutate(
      { title, layout: { title } },
      {
        onSuccess: (record) => {
          writeDraft(record.pipeline_id, draft);
          navigate({ area: "studio", pipelineId: record.pipeline_id });
        },
      },
    );
  }

  return {
    start,
    pending: create.isPending,
    error: create.error,
    retry: () => {
      if (attempt) start(attempt.title, attempt.draft);
    },
  };
}
