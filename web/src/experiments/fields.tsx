import { useId, type ComponentProps, type ReactNode } from "react";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";

/** A tick box with its text. The text names the box for assistive technology. */
export function Check({ checked, onChange, children }: { checked: boolean; onChange: (checked: boolean) => void; children: ReactNode }) {
  return (
    <label className="flex items-start gap-2 text-ui">
      <input type="checkbox" checked={checked} className="mt-0.5 size-4 shrink-0 accent-primary" onChange={(event) => onChange(event.target.checked)} />
      <span>{children}</span>
    </label>
  );
}

interface TextFieldProps extends Omit<ComponentProps<typeof Input>, "onChange" | "id"> {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: ReactNode;
  /** A friendly line shown beside the field and tied to it with `aria-describedby`. */
  error?: string | null;
}

/** A labelled text field with an optional hint and an error line tied to it. */
export function TextField({ label, value, onChange, hint, error, ...rest }: TextFieldProps) {
  const id = useId();
  const describedBy = [hint !== undefined ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean).join(" ");
  return (
    <div className="flex min-w-48 flex-1 flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} value={value} aria-invalid={error ? true : undefined} aria-describedby={describedBy || undefined} onChange={(event) => onChange(event.target.value)} {...rest} />
      {hint !== undefined ? (
        <p id={`${id}-hint`} className="text-meta text-muted-foreground">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-meta text-status-error-label">
          {error}
        </p>
      ) : null}
    </div>
  );
}

interface SelectFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly { value: string; label: string }[];
  /** For paths, which read left to right in any language. */
  ltr?: boolean;
}

/** A labelled select. The visible value is the selected option's label. */
export function SelectField({ label, value, onChange, options, ltr = false }: SelectFieldProps) {
  const id = useId();
  return (
    <div className="flex min-w-48 flex-1 flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id} dir={ltr ? "ltr" : undefined}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value} dir={ltr ? "ltr" : undefined}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
