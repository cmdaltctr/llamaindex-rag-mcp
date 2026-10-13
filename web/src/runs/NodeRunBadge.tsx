import { maskText } from "./redact";
import { bypassReason, displayStatus, statusLabel, type NodeRunState } from "./runState";
import "./runs.css";

/**
 * The run state of one node, as text. Status words carry the meaning, so
 * nothing depends on colour or motion. Reasons and errors render as text.
 */
export function NodeRunBadge({ state }: { state: NodeRunState | undefined }) {
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
    <p className="run-badge" data-run-status={status ?? "not-started"}>
      <span className="run-badge__status">{statusLabel(status)}</span>
      {detail ? <span className="run-badge__detail">{`: ${maskText(detail)}`}</span> : null}
    </p>
  );
}
