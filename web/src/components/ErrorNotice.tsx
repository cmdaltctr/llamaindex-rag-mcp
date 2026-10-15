import { useMemo } from "react";
import { describeError } from "../lib/errors";
import { Button } from "./ui/button";

interface ErrorNoticeProps {
  error: unknown;
  onRetry?: () => void;
  /** Where "Go back" leads for a missing resource: the picker of the view. */
  backHref?: string;
  onChooseFile?: () => void;
}

/** One friendly line and one action for any failure. The raw message goes to the console only. */
export function ErrorNotice({ error, onRetry, backHref, onChooseFile }: ErrorNoticeProps) {
  const friendly = useMemo(() => describeError(error), [error]);
  const { kind, label } = friendly.action;

  // Every failure carries exactly one action. When the caller wires none, fall
  // back to one that always works: Home for a missing resource, a reload otherwise.
  const reload = <Button variant="outline" onClick={() => window.location.reload()}>Reload the page</Button>;
  let action = reload;
  if (kind === "retry" && onRetry) action = <Button variant="outline" onClick={onRetry}>{label}</Button>;
  else if (kind === "reload") action = <Button variant="outline" onClick={() => window.location.reload()}>{label}</Button>;
  else if (kind === "back") {
    action = (
      <Button asChild variant="outline">
        <a href={backHref ?? "#/home"}>{backHref === undefined ? "Go to Home" : label}</a>
      </Button>
    );
  } else if (kind === "choose-file" && onChooseFile) action = <Button variant="outline" onClick={onChooseFile}>{label}</Button>;

  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-panel border border-status-error bg-status-error/10 px-4 py-3">
      <p className="text-ui text-status-error-label">{friendly.message}</p>
      {action}
    </div>
  );
}
