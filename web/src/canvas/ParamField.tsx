import { useId, useState } from "react";
import type { EffectiveControl, JsonValue } from "../api/pipelines";
import { checkValue, type ParamField as Field } from "./schema";

interface ParamFieldProps {
  field: Field;
  value: JsonValue | undefined;
  effective: EffectiveControl | undefined;
  onChange: (value: JsonValue) => void;
}

function display(value: JsonValue): string {
  if (value === true) return "On";
  if (value === false) return "Off";
  return typeof value === "string" ? value : JSON.stringify(value);
}

function InheritNote({ field, effective }: { field: Field; effective: EffectiveControl | undefined }) {
  if (effective) {
    return (
      <p className="text-meta param__note">
        Effective value: {display(effective.value)} ({effective.source}: {effective.detail}), from the last validation.
      </p>
    );
  }
  if (!field.nullable) return null;
  return (
    <p className="text-meta param__note">
      {field.lever
        ? "Inherit uses the graph override or the profile. Validate with run inputs to see the effective value."
        : "Inherit uses the operation default."}
    </p>
  );
}

function TriState({ value, onChange, name }: ParamFieldProps & { name: string }) {
  const options: [string, JsonValue][] = [
    ["Inherit", null],
    ["On", true],
    ["Off", false],
  ];
  const current = value ?? null;
  return (
    <div className="param__choices">
      {options.map(([label, option]) => (
        <label key={label} className="param__choice">
          <input type="radio" name={name} checked={current === option} onChange={() => onChange(option)} />
          {label}
        </label>
      ))}
    </div>
  );
}

function NumberInput({ field, value, onChange, name }: ParamFieldProps & { name: string }) {
  const [inherit, setInherit] = useState(field.nullable && value == null);
  const [text, setText] = useState(value == null ? "" : String(value));
  const [error, setError] = useState<string | null>(null);
  const errorId = `${name}-error`;

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
        <div className="param__choices">
          <label className="param__choice">
            <input type="radio" name={name} checked={inherit} onChange={chooseInherit} />
            Inherit
          </label>
          <label className="param__choice">
            <input type="radio" name={name} checked={!inherit} onChange={() => setInherit(false)} />
            Set value
          </label>
        </div>
      )}
      <label className="field">
        <span className="field__label">{`${field.title} value`}</span>
        <input
          className="control"
          type="text"
          inputMode={field.kind === "integer" ? "numeric" : "decimal"}
          value={text}
          disabled={inherit}
          placeholder={field.defaultValue != null ? String(field.defaultValue) : undefined}
          aria-invalid={error !== null}
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => update(event.target.value)}
        />
      </label>
      {error && (
        <p id={errorId} className="canvas-error text-meta">
          {error}
        </p>
      )}
    </>
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
      <label className="param__choice">
        <input type="checkbox" checked={Boolean(value ?? field.defaultValue)} onChange={(event) => onChange(event.target.checked)} />
        {field.title}
      </label>
    );
  } else if (field.kind === "integer" || field.kind === "number") control = <NumberInput {...props} name={name} />;
  else if (field.kind === "enum" || field.kind === "string") {
    control =
      field.kind === "enum" ? (
        <select className="control control--select" aria-label={`${field.title} value`} value={value == null ? "" : String(value)} onChange={(event) => onChange(event.target.value || null)}>
          {field.nullable && <option value="">Inherit</option>}
          {field.options.map((option) => (
            <option key={String(option)} value={String(option)}>
              {String(option)}
            </option>
          ))}
        </select>
      ) : (
        <input className="control" aria-label={`${field.title} value`} value={value == null ? "" : String(value)} placeholder={field.nullable ? "Inherit" : undefined} onChange={(event) => onChange(event.target.value || null)} />
      );
  } else control = <p className="text-meta">This parameter type cannot be edited on the canvas yet.</p>;

  return (
    <fieldset className="param">
      <legend className="param__legend">{field.title}</legend>
      {field.lever && <code className="param__lever">{field.lever}</code>}
      {control}
      <InheritNote field={field} effective={props.effective} />
    </fieldset>
  );
}
