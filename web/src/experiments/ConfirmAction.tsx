import { useState } from "react";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";

interface ConfirmActionProps {
  /** Accessible name of the first button, for example "Revoke chunks". */
  label: string;
  /** Visible text of the first button. */
  text: string;
  warning: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => Promise<unknown>;
}

/** A button that asks once more before it acts. Nothing is sent until the user confirms. */
export function ConfirmAction({ label, text, warning, confirmLabel, cancelLabel, onConfirm }: ConfirmActionProps) {
  const [phase, setPhase] = useState<"idle" | "asking" | "working">("idle");
  const [error, setError] = useState<unknown>(null);

  async function confirm() {
    setPhase("working");
    setError(null);
    try {
      await onConfirm();
      setPhase("idle");
    } catch (failure) {
      setError(failure);
      setPhase("asking");
    }
  }

  if (phase === "idle") {
    return (
      <Button variant="ghost" size="sm" aria-label={label} onClick={() => setPhase("asking")}>
        {text}
      </Button>
    );
  }
  return (
    <div role="group" aria-label={label} className="flex max-w-prose flex-col gap-2">
      <p className="text-meta text-muted-foreground">{warning}</p>
      {error !== null ? <ErrorNotice error={error} /> : null}
      <div className="flex flex-wrap gap-2">
        <Button variant="destructive" size="sm" disabled={phase === "working"} onClick={() => void confirm()}>
          {confirmLabel}
        </Button>
        <Button variant="outline" size="sm" disabled={phase === "working"} onClick={() => setPhase("idle")}>
          {cancelLabel}
        </Button>
      </div>
    </div>
  );
}
