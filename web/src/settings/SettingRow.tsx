import { useId, useState, type FormEvent } from "react";
import { Badge } from "../components/ui/badge";
import { CardInset } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { isEnvironmentSource, sourceText } from "./connectionWords";
import { SaveErrorNotice } from "./SaveErrorNotice";
import { SettingControl, type SettingKind } from "./SettingControl";
import { numberIn, rangeRule, wholeNumberIn } from "./validation";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";
const SOURCE = "text-meta text-muted-foreground";

export interface SettingRowProps {
  label: string;
  /** The value in force, as text. Edit opens an input filled with it. A `bool` row takes `true` or `false`. */
  value: string;
  source: string;
  /** A variable name or path that goes after the source words. */
  detail?: string | null;
  inputType?: "text" | "number";
  /** The control Edit opens. Left out, the row keeps a text or number input from `inputType`. */
  kind?: SettingKind;
  /** The accepted values of a `choice` row. */
  choices?: string[] | null;
  min?: number | null;
  max?: number | null;
  /** Makes the row read-only and says why, for example a missing session scope. */
  readOnlyReason?: string | null;
  /** Shows "Restart to apply": the saved value applies after a restart. */
  restartPending?: boolean;
  /**
   * The value the next launch uses, as text, or `null` for the default. Shown
   * beside "Restart to apply", and Edit opens with it. Left out, Edit opens with `value`.
   */
  saved?: string | null;
  pending: boolean;
  error: unknown;
  /** Called with the typed text; the row closes its input when `done` runs. */
  onSave: (text: string, done: () => void) => void;
  /** Returns the setting to its default. The row offers it only for a value from `omrs.jsonc`. */
  onClear?: (done: () => void) => void;
  /** The words on the clear button. */
  clearLabel?: string;
  onRetry: () => void;
  /** Checked before Save sends anything. A returned message shows under the input and nothing is saved. */
  validate?: (text: string) => string | null;
  /** Called with the typed text as it changes, and with `null` when the input closes. */
  onTyped?: (text: string | null) => void;
}

/** The control for a row: `kind` when given, else the input that `inputType` names. */
function controlKind(kind: SettingKind | undefined, inputType: "text" | "number"): SettingKind {
  return kind ?? (inputType === "number" ? "int" : "text");
}

/** The check of a number row with no `validate` of its own: its range rule. A row given `kind` gets it; an old `inputType` row does not. */
function rangeCheck(kind: SettingKind | undefined, min: number | null, max: number | null): ((text: string) => string | null) | undefined {
  if (kind === "int") return wholeNumberIn(min, max, rangeRule(min, max, true));
  if (kind === "float") return numberIn(min, max, rangeRule(min, max, false));
  return undefined;
}

function shownValue(kind: SettingKind | undefined, value: string): string {
  if (kind === "bool" && (value === "true" || value === "false")) return value === "true" ? "On" : "Off";
  return value;
}

/**
 * One setting: the label, the value in force, where the value comes from and Edit.
 * The input exists only after Edit and starts filled with the value, so it is
 * never empty for a setting that has one. A value from the environment or
 * `.env` has no Edit; the source words say where to change it.
 */
export function SettingRow(props: SettingRowProps) {
  const { label, value, source, detail, inputType = "text", kind, choices, min = null, max = null, readOnlyReason, restartPending = false, saved, pending, error } = props;
  const { onSave, onClear, clearLabel = "Use default", onRetry, onTyped } = props;
  const validate = props.validate ?? rangeCheck(kind, min, max);
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
  const start = saved ?? value;
  const dirty = typed !== null && typed !== start && typed.trim() !== "";

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!dirty || typed === null) return;
    const message = validate?.(typed) ?? null;
    if (message !== null) return setRefusal(message);
    onSave(typed, close);
  }

  return (
    <CardInset>
      {editing ? (
        <form onSubmit={submit} noValidate className="flex flex-col gap-1.5">
          <Label htmlFor={id}>{label}</Label>
          <SettingControl id={id} label={label} kind={controlKind(kind, inputType)} typed={typed} choices={choices ?? []} min={min} max={max} refusal={refusal} onChange={change} />
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
                {clearLabel}
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
              {shownValue(kind, value)}
            </code>
          )}
          <p className={SOURCE}>{sourceText(source, detail)}</p>
          {restartPending ? (
            <div className="flex flex-wrap items-center gap-2">
              {saved !== undefined ? (
                <p className="text-ui">
                  {"Saved for the next launch: "}
                  <code dir="ltr" className={CODE}>
                    {saved === null ? "default" : shownValue(kind, saved)}
                  </code>
                </p>
              ) : null}
              <Badge variant="warning">Restart to apply</Badge>
            </div>
          ) : null}
          {readOnlyReason ? <p className={SOURCE}>{readOnlyReason}</p> : null}
          {!locked ? (
            <div>
              <Button type="button" variant="outline" size="sm" aria-label={`Edit ${label}`} onClick={() => setTyped(start)}>
                Edit
              </Button>
            </div>
          ) : null}
        </>
      )}
      {error ? <SaveErrorNotice error={error} onRetry={onRetry} /> : null}
    </CardInset>
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
    <CardInset>
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
    </CardInset>
  );
}
