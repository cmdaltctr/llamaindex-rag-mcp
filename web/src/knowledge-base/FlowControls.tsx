import type { Confirmation } from "../api/documents";
import { AlertNotice } from "../components/AlertNotice";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import type { FlowState } from "./usePreviewConfirm";

const STALE =
  "This preview is out of date. The collection changed, or the preview expired or was used already. Nothing was changed. Preview again to continue.";
const REQUIRED = "The server needs a fresh preview before it changes anything. Nothing was changed. Preview again to continue.";

/** States the guarantee behind a preview token, including the weaker process-local one. */
export function ConfirmationNote({ confirmation }: { confirmation: Confirmation | undefined }) {
  if (confirmation === undefined) {
    return <p className="text-meta text-muted-foreground">The server issued no confirmation for this preview.</p>;
  }
  const minutes = Math.max(1, Math.round(confirmation.expires_in / 60));
  return (
    <div className="flex flex-col gap-2">
      <p className="text-meta text-muted-foreground">
        Nothing has changed yet. This preview stays valid for {minutes} {minutes === 1 ? "minute" : "minutes"} and only while
        the collection stays unchanged.
      </p>
      {confirmation.validity === "process_local" ? (
        <div className="rounded-small border border-status-warning bg-status-warning/10 px-3 py-2 text-meta text-status-warning-label">
          <strong className="block">Weaker guarantee</strong>
          <span>{confirmation.warning ?? "A change made by another process may go undetected."}</span>
        </div>
      ) : null}
    </div>
  );
}

interface FlowButtonsProps<P, R> {
  state: FlowState<P, R>;
  confirmLabel: string;
  canConfirm: boolean;
  onConfirm: () => void;
  onPreviewAgain: () => void;
  onCancel: () => void;
}

/** Confirm, Preview again and Cancel, shown according to the flow phase, with one friendly line for a failure. */
export function FlowButtons<P, R>({ state, confirmLabel, canConfirm, onConfirm, onPreviewAgain, onCancel }: FlowButtonsProps<P, R>) {
  const busy = state.phase === "previewing" || state.phase === "confirming";
  const failure = state.failure;
  return (
    <>
      {failure?.kind === "stale" || failure?.kind === "required" ? (
        <AlertNotice message={failure.kind === "stale" ? STALE : REQUIRED}>
          <Button variant="outline" onClick={onPreviewAgain}>
            Preview again
          </Button>
        </AlertNotice>
      ) : null}
      {failure?.kind === "other" ? <ErrorNotice error={failure.error} onRetry={onPreviewAgain} /> : null}
      {busy ? (
        <p role="status" className="text-meta text-muted-foreground">
          {state.phase === "previewing" ? "Preparing the preview." : "Applying the change."}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {state.phase === "ready" && canConfirm ? (
          <Button variant="destructive" onClick={onConfirm}>
            {confirmLabel}
          </Button>
        ) : null}
        <Button variant="ghost" onClick={onCancel} disabled={busy}>
          {state.phase === "done" ? "Close" : "Cancel"}
        </Button>
      </div>
    </>
  );
}
