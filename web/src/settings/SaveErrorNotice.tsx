import { useMemo } from "react";
import { describeSaveError } from "../lib/errors";
import { Button } from "../components/ui/button";

interface SaveErrorNoticeProps {
  error: unknown;
  onRetry: () => void;
}

/**
 * One line and one action for a failed Settings save. A 400 or 409 shows the
 * server's message; every other failure keeps the generic text. The action
 * reloads the page for a conflict and retries otherwise.
 */
export function SaveErrorNotice({ error, onRetry }: SaveErrorNoticeProps) {
  const friendly = useMemo(() => describeSaveError(error), [error]);
  const { kind, label } = friendly.action;
  const onClick = kind === "reload" ? () => window.location.reload() : onRetry;

  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-panel border border-status-error bg-status-error/10 px-4 py-3">
      <p className="text-ui text-status-error-label">{friendly.message}</p>
      <Button type="button" variant="outline" size="sm" onClick={onClick}>
        {kind === "retry" || kind === "reload" ? label : "Try again"}
      </Button>
    </div>
  );
}
