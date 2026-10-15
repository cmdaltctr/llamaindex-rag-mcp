import { Badge } from "../components/ui/badge";
import { maskText } from "../runs/redact";
import { bypassReason, displayStatus, statusLabel, type NodeDisplayStatus, type NodeRunState } from "../runs/runState";

const VARIANT: Record<NodeDisplayStatus, "neutral" | "info" | "success" | "error" | "warning"> = {
  queued: "neutral",
  running: "info",
  succeeded: "success",
  failed: "error",
  skipped: "neutral",
  bypassed: "neutral",
  cancelled: "warning",
  fallback: "warning",
};

/**
 * The run state of one node, as text first: only events set a state, and a
 * node with no event reads "Not started". Reasons and errors are text.
 */
export function NodeRunStatus({ state }: { state: NodeRunState | undefined }) {
  const status = displayStatus(state);
  const detail =
    status === "fallback"
      ? state?.fallback
      : status === "failed"
        ? state?.error
        : status === "skipped"
          ? state?.message
          : status === "bypassed"
            ? (bypassReason(state) ?? "input passed through unchanged")
            : null;
  return (
    <p className="flex flex-wrap items-center gap-x-0.5" data-run-status={status ?? "not-started"}>
      <Badge variant={status ? VARIANT[status] : "neutral"}>{statusLabel(status)}</Badge>
      {detail ? <span className="min-w-0 text-meta text-muted-foreground [overflow-wrap:anywhere]">{`: ${maskText(detail)}`}</span> : null}
    </p>
  );
}
