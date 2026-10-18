import type { ServerField } from "../api/llamacppServer";
import { useSaveLlamacppServer } from "../api/llamacppServerHooks";
import { EditableValue } from "./EditableValue";

type Key = "binary" | "model" | "context_window";

interface FieldRow {
  key: Key;
  /** Words used in the button and source line names, such as "program path". */
  noun: string;
  inputType: "text" | "number";
}

const ROWS: FieldRow[] = [
  { key: "binary", noun: "program path", inputType: "text" },
  { key: "model", noun: "model", inputType: "text" },
  { key: "context_window", noun: "context window", inputType: "number" },
];

function sourceLine(field: ServerField): string {
  return `${field.label.replace(/ \(tokens\)$/, "")} source: ${field.source}`;
}

/** The program path, the model and the context window of the managed server, each saved on its own. */
export function LlamacppServerFields({ saved }: { saved: Record<Key, ServerField> }) {
  const save = useSaveLlamacppServer();
  return (
    <>
      {ROWS.map((row) => {
        const field = saved[row.key];
        const apply = (value: string | number | null, done: () => void) => save.mutate({ [row.key]: value }, { onSuccess: done });
        return (
          <EditableValue
            key={row.key}
            label={field.label}
            value={String(field.value)}
            source={field.source}
            locked={field.locked}
            lockReason={field.lock_reason}
            inputType={row.inputType}
            min={field.min}
            max={field.max}
            saveLabel={`Save ${row.noun}`}
            resetLabel={`Reset ${row.noun}`}
            sourceLabel={sourceLine(field)}
            pending={save.isPending}
            error={save.isError && save.variables !== undefined && row.key in save.variables ? save.error : null}
            onSave={(text, done) => apply(row.inputType === "number" ? Number(text) : text, done)}
            onReset={(done) => apply(null, done)}
            onRetry={() => save.reset()}
          />
        );
      })}
    </>
  );
}
