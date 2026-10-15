import { ErrorNotice } from "../components/ErrorNotice";

/**
 * What the last canvas action reported. A `refused` notice carries our own
 * explanation (for example why two ports cannot connect). A `failure` carries
 * the error itself, which `ErrorNotice` turns into one friendly line.
 */
export type Notice =
  | { kind: "status"; text: string }
  | { kind: "refused"; text: string }
  | { kind: "failure"; error: unknown; retry?: () => void };

/** The one status line (polite) and the one alert of the canvas page. */
export function Notices({ notice }: { notice: Notice | null }) {
  return (
    <div className="flex flex-col gap-2">
      <p role="status" className="min-h-5 text-meta text-muted-foreground">
        {notice?.kind === "status" ? notice.text : ""}
      </p>
      {notice?.kind === "refused" && (
        <p role="alert" className="rounded-panel border border-status-error bg-status-error/10 px-4 py-3 text-ui text-status-error-label">
          {notice.text}
        </p>
      )}
      {notice?.kind === "failure" && <ErrorNotice error={notice.error} onRetry={notice.retry} />}
    </div>
  );
}
