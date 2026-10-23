import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useId } from "react";
import { useApi } from "../api/ApiProvider";
import type { ReasoningSetting } from "../api/settings";
import { reasoningLevelsQuery } from "../api/queries";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { SOURCE } from "./ChoiceRow";

// A Radix select item cannot have the empty value, so "Provider default" uses this one.
const DEFAULT_VALUE = "__provider_default__";

/** The saved reasoning state that the form opens with. */
export interface ReasoningState {
  /** `""` means the provider default. */
  value: string;
  locked: boolean;
  lockReason: string | null;
  /** True when the saved provider does not send the level. */
  ignored: boolean;
}

interface ReasoningFieldProps {
  provider: string;
  model: string;
  value: string;
  onChange: (value: string) => void;
  state: ReasoningState;
  /** The provider the saved `ignored` flag describes. */
  savedProvider: string;
}

/** The reasoning level shown as read-only words, such as `low` or `Provider default`. */
export function reasoningText(value: string | undefined): string {
  return value === undefined || value === "" ? "Provider default" : value;
}

/** The reasoning state of a Chat or judge read. A server before the reasoning change sends none of the fields. */
export function reasoningState(settings: ReasoningSetting): ReasoningState {
  return {
    value: settings.reasoning ?? "",
    locked: settings.reasoning_locked ?? false,
    lockReason: settings.reasoning_lock_reason ?? null,
    ignored: settings.reasoning_ignored ?? false,
  };
}

/** The saved level as one read-only line, with the lock reason when the environment sets it. */
export function ReasoningLine({ settings }: { settings: ReasoningSetting }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-ui">
        Reasoning:{" "}
        <code dir="ltr" className="font-mono text-code">
          {reasoningText(settings.reasoning)}
        </code>
      </p>
      {settings.reasoning_locked ? <p className={SOURCE}>{settings.reasoning_lock_reason ?? "Read-only here."}</p> : null}
    </div>
  );
}

/**
 * The Reasoning control under the model name. A dropdown when the catalogue
 * knows the model's levels, a text box when it does not, read-only when the
 * environment sets the level.
 */
export function ReasoningField({ provider, model, value, onChange, state, savedProvider }: ReasoningFieldProps) {
  const api = useApi();
  const id = useId();
  const levels = useQuery({ ...reasoningLevelsQuery(api, provider, model), enabled: provider !== "" && model !== "" && !state.locked, placeholderData: keepPreviousData });
  const known = levels.data?.known === true ? levels.data : null;

  let control;
  if (state.locked) {
    control = <Input id={id} dir="ltr" readOnly className="max-w-xs" value={reasoningText(value)} />;
  } else if (known !== null) {
    // A saved level the model no longer lists stays visible, so opening the form never changes it.
    const options = value === "" || known.levels.includes(value) ? known.levels : [...known.levels, value];
    control = (
      <Select value={value === "" ? DEFAULT_VALUE : value} onValueChange={(next) => onChange(next === DEFAULT_VALUE ? "" : next)}>
        <SelectTrigger id={id} className="max-w-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={DEFAULT_VALUE}>{known.default === null ? "Provider default" : `Provider default (${known.default})`}</SelectItem>
          {options.map((level) => (
            <SelectItem key={level} value={level}>
              {level}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  } else {
    control = <Input id={id} dir="ltr" autoComplete="off" spellCheck={false} placeholder="Provider default" className="max-w-xs" value={value} onChange={(event) => onChange(event.target.value.trim())} />;
  }

  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>Reasoning</Label>
      {control}
      {state.locked ? <p className={SOURCE}>{state.lockReason ?? "Read-only here."}</p> : null}
      {!state.locked && known === null ? <p className={SOURCE}>Type a level the model accepts, such as low or high. Leave it empty for the provider default.</p> : null}
      {(levels.data?.ignored ?? (state.ignored && provider === savedProvider)) ? <p className={SOURCE}>This provider ignores the reasoning level. The model uses its own setting.</p> : null}
    </div>
  );
}
