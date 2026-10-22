import { useId, useState, type FormEvent } from "react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { isEnvironmentSource, sourceText } from "./connectionWords";
import { SaveErrorNotice } from "./SaveErrorNotice";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";
const SOURCE = "text-meta text-muted-foreground";

export interface SettingRowProps {
  label: string;
  /** The value in force, as text. Edit opens an input filled with it. */
  value: string;
  source: string;
  /** The variable name or the path that goes after the source words. */
  detail?: string | null;
  inputType?: "text" | "number";
  min?: number | null;
  max?: number | null;
  /** Makes the row read-only and says why, for example a missing session scope. */
  readOnlyReason?: string | null;
  pending: boolean;
  error: unknown;
  /** Called with the typed text; the row closes its input when `done` runs. */
  onSave: (text: string, done: () => void) => void;
  /** Returns the setting to its default. The row offers it only for a value from `omrs.jsonc`. */
  onClear?: (done: () => void) => void;
  onRetry: () => void;
  /** Checked before Save sends anything. A returned message shows under the input and nothing is saved. */
  validate?: (text: string) => string | null;
  /** Called with the typed text as it changes, and with `null` when the input closes. */
  onTyped?: (text: string | null) => void;
}

/**
 * One setting: label, value in force, where the value comes from and Edit.
 * The input exists only after Edit and starts filled with the value, so it is
 * never empty for a setting that has one. A value from the environment or
 * `.env` has no Edit; the source words say where to change it.
 */
export function SettingRow(props: SettingRowProps) {
  const { label, value, source, detail, inputType = "text", min, max, readOnlyReason, pending, error, onSave, onClear, onRetry, validate, onTyped } = props;
  const id = useId();
  const [typed, setTyped] = useState<string | null>(null);
  const editing = typed !== null;
  const [refusal, setRefusal] = useState<string | null>(null);
  const change = (text: string) => {
    setTyped(text);
    setRefusal(null);
    onTyped?.(text);
  };
  const close = () => {
    setTyped(null);
    setRefusal(null);
    onTyped?.(null);
  };
  const locked = isEnvironmentSource(source) || (readOnlyReason ?? null) !== null;
  const dirty = typed !== null && typed !== value && typed.trim() !== "";

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!dirty || typed === null) return;
    const message = validate?.(typed) ?? null;
    if (message !== null) return setRefusal(message);
    onSave(typed, close);
  }

  return (
    <div className="flex flex-col gap-1.5">
      {editing ? (
        <form onSubmit={submit} noValidate className="flex flex-col gap-1.5">
          <Label htmlFor={id}>{label}</Label>
          <Input
            id={id}
            dir="ltr"
            autoComplete="off"
            spellCheck={false}
            type={inputType}
            {...(inputType === "number" ? { inputMode: "numeric" as const, step: 1, min: min ?? undefined, max: max ?? undefined } : {})}
            value={typed}
            onChange={(event) => change(event.target.value)}
            aria-invalid={refusal !== null}
            aria-describedby={refusal !== null ? `${id}-refusal` : undefined}
          />
          {refusal !== null ? (
            <p id={`${id}-refusal`} className="text-meta text-status-error-label">
              {refusal}
            </p>
          ) : null}
          <p className={SOURCE}>{sourceText(source, detail)}</p>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" size="sm" disabled={!dirty || pending}>
              Save
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={close}>
              Cancel
            </Button>
            {source === "config-file" && onClear !== undefined ? (
              <Button type="button" variant="outline" size="sm" disabled={pending} onClick={() => onClear(close)}>
                Use default
              </Button>
            ) : null}
          </div>
        </form>
      ) : (
        <>
          <p className={SOURCE}>{label}</p>
          {value === "" ? (
            <p className="text-ui">Not set</p>
          ) : (
            <code dir="ltr" className={CODE}>
              {value}
            </code>
          )}
          <p className={SOURCE}>{sourceText(source, detail)}</p>
          {readOnlyReason ? <p className={SOURCE}>{readOnlyReason}</p> : null}
          {!locked ? (
            <div>
              <Button type="button" variant="outline" size="sm" aria-label={`Edit ${label}`} onClick={() => setTyped(value)}>
                Edit
              </Button>
            </div>
          ) : null}
        </>
      )}
      {error ? <SaveErrorNotice error={error} onRetry={onRetry} /> : null}
    </div>
  );
}

export interface KeySettingRowProps {
  label: string;
  set: boolean;
  /** The last four characters of the key, or `null`. The page never holds more. */
  last4: string | null;
  source: string;
  /** The path of the key file, shown after the source words of a `key-file` key. */
  detail?: string | null;
  keychain: "available" | "unavailable";
  /** Where a key can be put by hand, for the hint and the no-keychain line. */
  keyFile: string;
  envVar: string;
  /** False for a key the provider can run without. */
  required?: boolean;
  pending: boolean;
  error: unknown;
  /** Called with the trimmed key; the row closes its input when `done` runs. */
  onSave: (key: string, done: () => void) => void;
  onRemove: () => void;
  onRetry: () => void;
  /** Called with the typed key as it changes, and with `null` when the input closes. */
  onTyped?: (key: string | null) => void;
}

/**
 * The key of one provider. A set key shows as the summary "Key set · ending
 * XXXX · source" with no input. Replace opens an empty password input; Remove
 * shows only for a key in the system keychain. A key from the environment or
 * `.env` has no button.
 */
export function KeySettingRow(props: KeySettingRowProps) {
  const { label, set, last4, source, detail, keychain, keyFile, envVar, required = true, pending, error, onSave, onRemove, onRetry, onTyped } = props;
  const id = useId();
  const [typed, setTyped] = useState<string | null>(null);
  const change = (text: string) => {
    setTyped(text);
    onTyped?.(text);
  };
  const close = () => {
    setTyped(null);
    onTyped?.(null);
  };
  const key = typed ?? "";
  const opened = typed !== null || !set;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (key.trim() !== "") onSave(key.trim(), close);
  }

  const summary = `Key set${last4 !== null ? ` · ending ${last4}` : ""} · ${sourceText(source, detail)}`;
  const noKeychain = !set && keychain === "unavailable";

  return (
    <div className="flex flex-col gap-1.5">
      {set ? <p className="text-ui">{summary}</p> : null}
      {noKeychain ? (
        <>
          <p className={SOURCE}>{label}</p>
          <p className="text-ui">{`No system keychain is available on this machine. Put the key in ${keyFile} or set ${envVar}.`}</p>
        </>
      ) : null}
      {opened && !noKeychain ? (
        <form onSubmit={submit} className="flex flex-col gap-1.5">
          <Label htmlFor={id}>{label}</Label>
          {required ? null : <p className={SOURCE}>Optional</p>}
          <Input
            id={id}
            type="password"
            dir="ltr"
            autoComplete="off"
            spellCheck={false}
            placeholder={set ? undefined : "Paste key (saved to the system keychain)"}
            value={key}
            onChange={(event) => change(event.target.value)}
          />
          {set ? null : <p className={SOURCE}>{`Or put it in ${keyFile}`}</p>}
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" size="sm" disabled={pending || key.trim() === ""}>
              Save key
            </Button>
            {set ? (
              <Button type="button" variant="outline" size="sm" onClick={close}>
                Cancel
              </Button>
            ) : null}
          </div>
        </form>
      ) : null}
      {set && typed === null && !isEnvironmentSource(source) ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" aria-label={`Replace ${label}`} onClick={() => setTyped("")}>
            Replace
          </Button>
          {source === "keychain" ? (
            <Button type="button" variant="outline" size="sm" aria-label={`Remove ${label}`} disabled={pending} onClick={onRemove}>
              Remove
            </Button>
          ) : null}
        </div>
      ) : null}
      {error ? <SaveErrorNotice error={error} onRetry={onRetry} /> : null}
    </div>
  );
}
