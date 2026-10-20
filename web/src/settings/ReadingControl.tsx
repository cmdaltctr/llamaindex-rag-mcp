import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import type { ReadingChoice, ReadingKind } from "./documentReadingWords";

const META = "text-meta text-muted-foreground";

interface ReadingControlProps {
  id: string;
  label: string;
  kind: ReadingKind;
  /** The editor text: a name, a number as text, or `true` / `false` for a switch. */
  draft: string;
  choices: ReadingChoice[];
  /** The refusal of the typed value, shown under a number input. */
  refusal: string | null;
  onChange: (text: string) => void;
}

/** The control that edits one document reading value. The row shows the visible label; the control carries it as its name. Nothing is saved until the row's Save. */
export function ReadingControl({ id, label, kind, draft, choices, refusal, onChange }: ReadingControlProps) {
  if (kind === "switch") {
    const on = draft === "true";
    return (
      <div className="flex flex-col gap-1.5">
        <div>
          <Button type="button" variant="outline" role="switch" aria-checked={on} aria-label={label} onClick={() => onChange(on ? "false" : "true")}>
            {on ? "On" : "Off"}
          </Button>
        </div>
      </div>
    );
  }

  if (kind === "fraction") {
    return (
      <div className="flex flex-col gap-1.5">
        <Input
          id={id}
          aria-label={label}
          dir="ltr"
          type="number"
          inputMode="decimal"
          step={0.01}
          min={0}
          max={1}
          autoComplete="off"
          className="max-w-40"
          value={draft}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={refusal !== null}
          aria-describedby={refusal !== null ? `${id}-refusal` : undefined}
        />
        <p className={META}>Allowed: 0 to 1.</p>
        {refusal !== null ? (
          <p id={`${id}-refusal`} className="text-meta text-status-error-label">
            {refusal}
          </p>
        ) : null}
      </div>
    );
  }

  const selected = choices.find((choice) => choice.value === draft);
  const blocked = choices.filter((choice) => choice.disabled);
  return (
    <div className="flex flex-col gap-1.5">
      {choices.length === 0 ? (
        <p className="text-ui">No OCR engine is known. Set OCR_WORKERS_DIR to the ocr-workers folder and provision an engine.</p>
      ) : (
        <Select value={draft} onValueChange={onChange}>
          <SelectTrigger aria-label={label} className="max-w-xs">
            <SelectValue placeholder="Choose one" />
          </SelectTrigger>
          <SelectContent>
            {choices.map((choice) => (
              <SelectItem key={choice.value} value={choice.value} disabled={choice.disabled}>
                {choice.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {kind === "engine" && selected?.reason ? <p className={META}>{`${selected.value}: ${selected.reason}`}</p> : null}
      {blocked.map((choice) => (
        <p key={choice.value} className={META}>{`${choice.value} is not available. ${choice.reason ?? ""}`.trim()}</p>
      ))}
    </div>
  );
}
