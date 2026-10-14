import { useState } from "react";
import { messageOf } from "../views/shared/labels";

interface ConfirmActionProps {
  /** Accessible name of the first button, for example "Revoke chunks". */
  label: string;
  /** Visible text of the first button. */
  text: string;
  warning: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => Promise<void>;
}

/** A button that asks once more before it acts. Nothing is sent until the user confirms. */
export function ConfirmAction({ label, text, warning, confirmLabel, cancelLabel, onConfirm }: ConfirmActionProps) {
  const [phase, setPhase] = useState<"idle" | "asking" | "working">("idle");
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setPhase("working");
    setError(null);
    try {
      await onConfirm();
      setPhase("idle");
    } catch (failure) {
      setError(messageOf(failure));
      setPhase("asking");
    }
  }

  if (phase === "idle") {
    return (
      <button type="button" className="button button--small button--ghost" aria-label={label} onClick={() => setPhase("asking")}>
        {text}
      </button>
    );
  }
  return (
    <div className="confirm-action" role="group" aria-label={label}>
      <p className="type-meta">{warning}</p>
      {error !== null ? (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="button-row">
        <button type="button" className="button button--small button--danger" disabled={phase === "working"} onClick={() => void confirm()}>
          {confirmLabel}
        </button>
        <button type="button" className="button button--small button--ghost" disabled={phase === "working"} onClick={() => setPhase("idle")}>
          {cancelLabel}
        </button>
      </div>
    </div>
  );
}
