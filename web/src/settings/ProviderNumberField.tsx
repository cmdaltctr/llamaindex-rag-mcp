import { useSaveProviderFields } from "../api/settingsMutations";
import type { ProviderField } from "../api/settings";
import { EditableValue } from "./EditableValue";

interface ProviderNumberFieldProps {
  provider: string;
  field: ProviderField;
}

/** One whole-number provider value, such as the Ollama context window. The server checks the range. */
export function ProviderNumberField({ provider, field }: ProviderNumberFieldProps) {
  const save = useSaveProviderFields(provider);
  return (
    <EditableValue
      label={field.label}
      value={String(field.value ?? "")}
      source={field.source}
      locked={field.locked}
      lockReason={field.lock_reason}
      inputType="number"
      min={field.min}
      max={field.max}
      saveLabel="Save value"
      resetLabel="Reset to default"
      sourceLabel={`Source: ${field.source}`}
      pending={save.isPending}
      error={save.isError ? save.error : null}
      onSave={(text, done) => save.mutate({ [field.id]: Number(text) }, { onSuccess: done })}
      onReset={(done) => save.mutate({ [field.id]: null }, { onSuccess: done })}
      onRetry={() => save.reset()}
    />
  );
}
