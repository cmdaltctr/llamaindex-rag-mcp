import { Button } from "../components/ui/button";
import { cn } from "../lib/utils";
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
  /** The id of a line that describes the field, such as its rule. Left out, the refusal line describes it while there is one. */
  describedBy?: string;
  /** Extra classes for a text, number or choice field, such as a width. */
  className?: string;
}

/** One editor for a setting value. The row owns the label, Save and Cancel; nothing is saved here. */
export function SettingControl({ id, label, kind, typed, choices, min, max, refusal, onChange, describedBy, className }: SettingControlProps) {
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
        <SelectTrigger id={id} aria-label={label} className={cn("max-w-xs", className)}>
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
      aria-label={label}
      className={className}
      dir="ltr"
      autoComplete="off"
      spellCheck={false}
      type={number ? "number" : "text"}
      {...(number ? { inputMode: kind === "int" ? ("numeric" as const) : ("decimal" as const), step: kind === "int" ? 1 : "any", min: min ?? undefined, max: max ?? undefined } : {})}
      value={typed}
      onChange={(event) => onChange(event.target.value)}
      aria-invalid={refusal !== null}
      aria-describedby={describedBy ?? (refusal !== null ? `${id}-refusal` : undefined)}
    />
  );
}
