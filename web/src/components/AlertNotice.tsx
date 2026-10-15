import type { ReactNode } from "react";

/** One alert line with an optional action, for failures that `describeError` does not cover. */
export function AlertNotice({ message, children }: { message: string; children?: ReactNode }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-panel border border-status-error bg-status-error/10 px-4 py-3">
      <p className="text-ui text-status-error-label">{message}</p>
      {children}
    </div>
  );
}
