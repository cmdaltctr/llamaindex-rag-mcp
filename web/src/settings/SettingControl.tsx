import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";

/** The control a setting row edits with. `text` is a plain input; `int` and `float` are number inputs. */
export type SettingKind = "bool" | "int" | "float" | "text" | "choice";

interface SettingControlProps {
  id: string;
  label: string;
  kind: SettingKind;
  /** The editor text: `true` / `false` for a switch, a number as text, or a name. */
  typed: string;
  choices: string[];
  min: number | null;
  max: number | null;
  refusal: string | null;
  onChange: (text: string) => void;
}

/** One editor for a setting value. The row owns the label, Save and Cancel; nothing is saved here. */
export function SettingControl({ id, label, kind, typed, choices, min, max, refusal, onChange }: SettingControlProps) {
  if (kind === "bool") {
    const on = typed === "true";
    return (
      <div>
        <Button id={id} type="button" variant="outline" size="sm" role="switch" aria-checked={on} aria-label={label} onClick={() => onChange(on ? "false" : "true")}>
          {on ? "On" : "Off"}
        </Button>
      </div>
    );
  }

  if (kind === "choice") {
    return (
      <Select value={typed} onValueChange={onChange}>
        <SelectTrigger id={id} aria-label={label} className="max-w-xs">
          <SelectValue placeholder="Choose one" />
        </SelectTrigger>
        <SelectContent>
          {choices.map((choice) => (
            <SelectItem key={choice} value={choice}>
              {choice}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }

  const number = kind === "int" || kind === "float";
  return (
    <Input
      id={id}
      dir="ltr"
      autoComplete="off"
      spellCheck={false}
      type={number ? "number" : "text"}
      {...(number ? { inputMode: kind === "int" ? ("numeric" as const) : ("decimal" as const), step: kind === "int" ? 1 : "any", min: min ?? undefined, max: max ?? undefined } : {})}
      value={typed}
      onChange={(event) => onChange(event.target.value)}
      aria-invalid={refusal !== null}
      aria-describedby={refusal !== null ? `${id}-refusal` : undefined}
    />
  );
}
