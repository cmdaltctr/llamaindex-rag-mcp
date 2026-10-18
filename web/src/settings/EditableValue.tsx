import { useId, useState, type FormEvent } from "react";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { lockedSourceLine } from "./connectionWords";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";

export interface EditableValueProps {
  /** Visible label and accessible name of the input. */
  label: string;
  /** The value the server holds, as text. */
  value: string;
  source: string;
  locked: boolean;
  lockReason: string | null;
  inputType: "text" | "number";
  min?: number | null;
  max?: number | null;
  /** Texts of the Save button, the Reset button and the source line. */
  saveLabel: string;
  resetLabel: string;
  sourceLabel: string;
  pending: boolean;
  error: unknown;
  /** Called with the typed text when Save is pressed; `onDone` clears the typed text after a good save. */
  onSave: (text: string, onDone: () => void) => void;
  onReset: (onDone: () => void) => void;
  onRetry: () => void;
}

/**
 * One editable provider value: an input with its label, a source line, Save
 * and Reset. A locked value shows its text, where it comes from and why it
 * cannot change here. The form skips browser validation, so the server is the
 * one judge of a value. It holds no provider name, so any field can use it.
 */
export function EditableValue(props: EditableValueProps) {
  const { label, value, source, locked, lockReason, inputType, min, max, saveLabel, resetLabel, sourceLabel, pending, error, onSave, onReset, onRetry } = props;
  const id = useId();
  const [typed, setTyped] = useState<string | undefined>(undefined);
  const text = typed ?? value;
  const dirty = typed !== undefined && typed !== value && typed.trim() !== "";
  const clear = () => setTyped(undefined);

  if (locked) {
    return (
      <div className="flex flex-col gap-1">
        <p className="text-meta text-muted-foreground">{label}</p>
        <code dir="ltr" className={CODE}>
          {value}
        </code>
        <p className="text-meta text-muted-foreground">
          <span>{source === "env" || source === "config-file" ? lockedSourceLine(source) : "Read-only"}</span>
          {lockReason !== null ? ` ${lockReason}` : ""}
        </p>
      </div>
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (dirty) onSave(text, clear);
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        dir="ltr"
        autoComplete="off"
        spellCheck={false}
        type={inputType}
        {...(inputType === "number" ? { inputMode: "numeric" as const, step: 1, min: min ?? undefined, max: max ?? undefined } : {})}
        value={text}
        onChange={(event) => setTyped(event.target.value)}
      />
      <p className="text-meta text-muted-foreground">{sourceLabel}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" disabled={!dirty || pending}>
          {saveLabel}
        </Button>
        {source === "saved" ? (
          <Button type="button" variant="outline" size="sm" disabled={pending} onClick={() => onReset(clear)}>
            {resetLabel}
          </Button>
        ) : null}
      </div>
      {error ? <ErrorNotice error={error} onRetry={onRetry} /> : null}
    </form>
  );
}
