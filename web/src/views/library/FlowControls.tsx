import type { Confirmation } from "../../api/documents";
import { ErrorNotice } from "../shared/controls";
import type { FlowState } from "./usePreviewConfirm";

/** States the guarantee behind a preview token, including the weaker process-local one. */
export function ConfirmationNote({ confirmation }: { confirmation: Confirmation | undefined }) {
  if (confirmation === undefined) {
    return <p className="text-meta">The server issued no confirmation for this preview.</p>;
  }
  const minutes = Math.max(1, Math.round(confirmation.expires_in / 60));
  return (
    <div className="confirmation-note">
      <p className="text-meta">
        Nothing has changed yet. This preview stays valid for {minutes} {minutes === 1 ? "minute" : "minutes"} and only while
        the collection stays unchanged.
      </p>
      {confirmation.validity === "process_local" ? (
        <p className="notice notice--warning">
          <strong>Weaker guarantee</strong>
          <span>{confirmation.warning ?? "A change made by another process may go undetected."}</span>
        </p>
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

/** Confirm, Preview again and Cancel, shown according to the flow phase. */
export function FlowButtons<P, R>({ state, confirmLabel, canConfirm, onConfirm, onPreviewAgain, onCancel }: FlowButtonsProps<P, R>) {
  const busy = state.phase === "previewing" || state.phase === "confirming";
  return (
    <>
      <ErrorNotice message={state.phase === "failed" ? (state.error ?? "The request failed.") : null} />
      {busy ? <p className="text-meta">{state.phase === "previewing" ? "Preparing the preview." : "Applying the change."}</p> : null}
      <div className="button-row">
        {state.phase === "ready" && canConfirm ? (
          <button type="button" className="button button--danger" onClick={onConfirm}>
            {confirmLabel}
          </button>
        ) : null}
        {state.phase === "failed" ? (
          <button type="button" className="button button--tinted" onClick={onPreviewAgain}>
            Preview again
          </button>
        ) : null}
        <button type="button" className="button button--ghost" onClick={onCancel} disabled={busy}>
          {state.phase === "done" ? "Close" : "Cancel"}
        </button>
      </div>
    </>
  );
}
