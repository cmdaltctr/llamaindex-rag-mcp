import { Panel, useReactFlow } from "@xyflow/react";
import { Columns3, Maximize2, Rows3, X } from "lucide-react";
import type { Ref } from "react";
import type { LayoutDirection } from "../api/pipelines";
import { Button } from "../components/ui/button";
import { useCanvasFullScreen } from "../lib/CanvasFullScreen";
import { arrangeLayout } from "./arrange";
import type { Draft } from "./graph";
import { setArrangement } from "./graph";
import { FULL_SCREEN_TOGGLE } from "./useFullScreenKeys";

interface ViewToolbarProps {
  draft: Draft;
  /** Measured step sizes from the flow surface. */
  sizes: Record<string, { width: number; height: number }>;
  onChange: (change: (draft: Draft) => Draft) => void;
  reducedMotion?: boolean;
  /** Focus target on entering full screen. */
  exitRef?: Ref<HTMLButtonElement>;
}

const OTHER: Record<LayoutDirection, LayoutDirection> = { horizontal: "vertical", vertical: "horizontal" };

/**
 * The canvas view controls at the top left. The arrange button names the
 * arrangement it will apply, moves the steps into layers, turns the connection
 * points to match and fits the view. It changes the draft layout only, so it
 * never makes a revision; a read-only canvas keeps the change for the visit.
 */
export function ViewToolbar({ draft, sizes, onChange, reducedMotion = false, exitRef }: ViewToolbarProps) {
  const { fitView } = useReactFlow();
  const { fullScreen, setFullScreen } = useCanvasFullScreen();
  const target = OTHER[draft.layout.direction];
  const Icon = target === "vertical" ? Rows3 : Columns3;

  function arrange() {
    const positions = arrangeLayout({
      nodeIds: draft.graph.nodes.map((node) => node.id),
      edges: draft.graph.edges.map((edge) => ({ source: edge.source.node, target: edge.target.node })),
      direction: target,
      sizes,
    });
    onChange((current) => setArrangement(current, positions, target));
    // Fit once React Flow has the new positions.
    requestAnimationFrame(() => void fitView({ duration: reducedMotion ? 0 : 200 }));
  }

  return (
    <Panel position="top-left">
      <div role="toolbar" aria-label="View controls" className="flex gap-1 rounded-control border border-border bg-card p-1 shadow-floating">
        <Button variant="ghost" size="icon-sm" aria-label={`Arrange ${target}ly`} title={`Arrange ${target}ly`} onClick={arrange}>
          <Icon aria-hidden="true" />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          data-slot={FULL_SCREEN_TOGGLE}
          aria-label="Full screen"
          title="Full screen"
          aria-pressed={fullScreen}
          onClick={() => setFullScreen(!fullScreen)}
        >
          <Maximize2 aria-hidden="true" />
        </Button>
        {fullScreen ? (
          <Button ref={exitRef} variant="ghost" size="icon-sm" aria-label="Exit full screen" title="Exit full screen" onClick={() => setFullScreen(false)}>
            <X aria-hidden="true" />
          </Button>
        ) : null}
      </div>
    </Panel>
  );
}
