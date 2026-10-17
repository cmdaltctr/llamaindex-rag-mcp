import { useId, useState } from "react";
import type { JsonValue } from "../api/pipelines";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { optionLabel } from "./labels";
import { checkValue, type ParamField as Field } from "./schema";

interface ParamFieldProps {
  field: Field;
  value: JsonValue | undefined;
  /** Where the value in use comes from, for example "Value in use: 10 (from profile)". `null` names no source. */
  note: string | null;
  onChange: (value: JsonValue) => void;
  /** Shows the value without allowing a change. */
  disabled?: boolean;
}

const INHERIT = "__inherit__";

function Choice({ type, name, checked, disabled, onChange, children }: { type: "radio" | "checkbox"; name?: string; checked: boolean; disabled?: boolean; onChange: (checked: boolean) => void; children: string }) {
  return (
    <label className="flex items-center gap-2 text-ui">
      <input type={type} name={name} checked={checked} disabled={disabled} className="size-4 accent-primary" onChange={(event) => onChange(event.target.checked)} />
      {children}
    </label>
  );
}

function InheritNote({ field, note }: { field: Field; note: string | null }) {
  const text = note ?? (field.nullable ? "Inherit uses the operation default." : null);
  return text === null ? null : <p className="text-meta text-muted-foreground">{text}</p>;
}

function TriState({ value, onChange, disabled, name }: ParamFieldProps & { name: string }) {
  const options: [string, JsonValue][] = [
    ["Inherit", null],
    ["On", true],
    ["Off", false],
  ];
  const current = value ?? null;
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1">
      {options.map(([label, option]) => (
        <Choice key={label} type="radio" name={name} checked={current === option} disabled={disabled} onChange={() => onChange(option)}>
          {label}
        </Choice>
      ))}
    </div>
  );
}

function NumberInput({ field, value, onChange, disabled, name }: ParamFieldProps & { name: string }) {
  const [inherit, setInherit] = useState(field.nullable && value == null);
  const [text, setText] = useState(value == null ? "" : String(value));
  const [error, setError] = useState<string | null>(null);
  const errorId = `${name}-error`;
  const inputId = `${name}-value`;

  function chooseInherit() {
    setInherit(true);
    setText("");
    setError(null);
    onChange(null);
  }

  function update(next: string) {
    setText(next);
    const result = checkValue(field, next);
    setError("error" in result ? result.error : null);
    if ("value" in result) onChange(result.value);
  }

  return (
    <>
      {field.nullable && (
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <Choice type="radio" name={name} checked={inherit} disabled={disabled} onChange={chooseInherit}>
            Inherit
          </Choice>
          <Choice type="radio" name={name} checked={!inherit} disabled={disabled} onChange={() => setInherit(false)}>
            Set value
          </Choice>
        </div>
      )}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={inputId}>{`${field.label} value`}</Label>
        <Input
          id={inputId}
          type="text"
          inputMode={field.kind === "integer" ? "numeric" : "decimal"}
          value={text}
          disabled={inherit || disabled}
          placeholder={field.defaultValue != null ? String(field.defaultValue) : undefined}
          aria-invalid={error !== null}
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => update(event.target.value)}
        />
      </div>
      {error && (
        <p id={errorId} className="text-meta text-status-error-label">
          {error}
        </p>
      )}
    </>
  );
}

function EnumSelect({ field, value, onChange, disabled }: ParamFieldProps) {
  const current = value == null ? INHERIT : String(value);
  return (
    <Select value={current} disabled={disabled} onValueChange={(next) => onChange(next === INHERIT ? null : next)}>
      <SelectTrigger aria-label={`${field.label} value`}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {field.nullable && <SelectItem value={INHERIT}>Inherit</SelectItem>}
        {field.options.map((option) => (
          <SelectItem key={String(option)} value={String(option)}>
            {optionLabel(field, option)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** One parameter control generated from the operation's JSON schema. */
export function ParamField(props: ParamFieldProps) {
  const { field, value, onChange } = props;
  const name = useId();
  let control;
  if (field.kind === "boolean" && field.nullable) control = <TriState {...props} name={name} />;
  else if (field.kind === "boolean") {
    control = (
      <Choice type="checkbox" checked={Boolean(value ?? field.defaultValue)} disabled={props.disabled} onChange={(checked) => onChange(checked)}>
        {field.label}
      </Choice>
    );
  } else if (field.kind === "integer" || field.kind === "number") control = <NumberInput {...props} name={name} />;
  else if (field.kind === "enum") control = <EnumSelect {...props} />;
  else if (field.kind === "string") {
    control = (
      <Input
        aria-label={`${field.label} value`}
        value={value == null ? "" : String(value)}
        placeholder={field.nullable ? "Inherit" : undefined}
        disabled={props.disabled}
        onChange={(event) => onChange(event.target.value || null)}
      />
    );
  } else control = <p className="text-meta text-muted-foreground">This parameter type cannot be edited on the canvas yet.</p>;

  return (
    <fieldset className="flex min-w-0 flex-col gap-2 rounded-control border border-border p-3">
      <legend className="px-1 text-ui font-medium">{field.label}</legend>
      {control}
      <InheritNote field={field} note={props.note} />
    </fieldset>
  );
}
