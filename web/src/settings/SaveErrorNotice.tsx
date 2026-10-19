import { useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { ApiError } from "../api/client";
import { reloadSettings } from "../api/settingsRevision";
import { describeSaveError } from "../lib/errors";
import { Button } from "../components/ui/button";

interface SaveErrorNoticeProps {
  error: unknown;
  onRetry: () => void;
}

/**
 * One line and one action for a failed Settings save. A 400 or 409 shows the
 * server's message; every other failure keeps the generic text. For a file
 * conflict (409) the action reads the Settings routes again and clears the
 * error, so the next save carries the new revision. For a refused session it
 * reloads the page; otherwise it retries.
 */
export function SaveErrorNotice({ error, onRetry }: SaveErrorNoticeProps) {
  const friendly = useMemo(() => describeSaveError(error), [error]);
  const queryClient = useQueryClient();
  const { kind, label } = friendly.action;
  const conflict = error instanceof ApiError && error.status === 409;
  const reload = () => {
    if (!conflict) return window.location.reload();
    void reloadSettings(queryClient);
    onRetry();
  };
  const onClick = kind === "reload" ? reload : onRetry;

  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-panel border border-status-error bg-status-error/10 px-4 py-3">
      <p className="text-ui text-status-error-label">{friendly.message}</p>
      <Button type="button" variant="outline" size="sm" onClick={onClick}>
        {kind === "retry" || kind === "reload" ? label : "Try again"}
      </Button>
    </div>
  );
}
