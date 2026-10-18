import { useReactFlow } from "@xyflow/react";
import { useEffect } from "react";

/** Asks the canvas to centre on a step. A new `n` makes a new request, even for the same step. */
export interface FocusRequest {
  id: string;
  n: number;
}

/** Renders nothing. Inside `ReactFlow`, it centres the view on the requested step. */
export function FocusStep({
  request,
  reducedMotion,
}: {
  request: FocusRequest | null;
  reducedMotion: boolean;
}) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    if (request === null) return;
    // Keep the zoom the user chose, up to a readable level, and move to the step.
    void fitView({
      nodes: [{ id: request.id }],
      duration: reducedMotion ? 0 : 250,
      maxZoom: 1.2,
      padding: 1.5,
    });
  }, [request, reducedMotion, fitView]);
  return null;
}
