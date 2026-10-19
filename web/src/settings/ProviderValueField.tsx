import { useSaveProviderFields } from "../api/settingsMutations";
import type { ProviderField } from "../api/settings";
import { SettingRow } from "./SettingRow";
import { formatCount, wholeNumberIn } from "./validation";

interface ProviderValueFieldProps {
  provider: string;
  field: ProviderField;
  /** The folder whose `.env` the server read; named when `.env` sets the value. */
  configDir: string;
  /** The text being typed, or `null` when the input closes. The card uses it for Test. */
  onTyped: (text: string | null) => void;
}

/** The message of an out-of-range whole number, such as "Enter 2,048 to 262,144.". */
function rangeMessage(field: ProviderField): string {
  return field.min !== null && field.max !== null ? `Enter ${formatCount(field.min)} to ${formatCount(field.max)}.` : "Enter a whole number.";
}

/**
 * One address (`url`) or whole number (`int`) of a provider as a setting row.
 * A value from the environment or `.env` is read-only; every other source can
 * be edited, and "Use default" removes the value from `omrg.jsonc`.
 */
export function ProviderValueField({ provider, field, configDir, onTyped }: ProviderValueFieldProps) {
  const save = useSaveProviderFields(provider);
  const isNumber = field.kind === "int";

  return (
    <SettingRow
      label={field.label}
      value={String(field.value ?? "")}
      source={field.source}
      detail={field.source === "dotenv" ? `${configDir}/.env` : null}
      readOnlyReason={field.locked ? (field.lock_reason ?? "Read-only") : null}
      inputType={isNumber ? "number" : "text"}
      min={field.min}
      max={field.max}
      validate={isNumber ? wholeNumberIn(field.min, field.max, rangeMessage(field)) : undefined}
      pending={save.isPending}
      error={save.isError ? save.error : null}
      onTyped={onTyped}
      onSave={(text, done) => save.mutate({ [field.id]: isNumber ? Number(text) : text }, { onSuccess: done })}
      onClear={(done) => save.mutate({ [field.id]: null }, { onSuccess: done })}
      onRetry={() => save.reset()}
    />
  );
}
