import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import type { ServerField } from "../api/llamacppServer";
import { useSaveLlamacppServer } from "../api/llamacppServerHooks";
import { sessionQuery } from "../api/queries";
import { SettingRow } from "./SettingRow";

type Key = "binary" | "model" | "context_window" | "idle_sleep";

interface FieldRow {
  key: Key;
  inputType: "text" | "number";
  /** True when changing it needs the `credentials` scope, because it decides which program the server runs. */
  needsCredentials: boolean;
}

const ROWS: FieldRow[] = [
  { key: "binary", inputType: "text", needsCredentials: true },
  { key: "model", inputType: "text", needsCredentials: true },
  { key: "context_window", inputType: "number", needsCredentials: false },
  { key: "idle_sleep", inputType: "number", needsCredentials: false },
];

const NEEDS_CREDENTIALS = "A credentials session is needed to change this.";

/** Why a row cannot be edited, or `null`. A locked field gives the server's reason. */
function readOnlyReason(field: ServerField, row: FieldRow, hasCredentials: boolean): string | null {
  if (field.locked) return field.lock_reason ?? "Read-only";
  return row.needsCredentials && !hasCredentials ? NEEDS_CREDENTIALS : null;
}

/** The program path, model, context window and idle sleep of the managed server, each a setting row saved on its own. */
export function LlamacppServerFields({ saved }: { saved: Record<Key, ServerField> }) {
  const save = useSaveLlamacppServer();
  const session = useQuery(sessionQuery(useApi()));
  // Until the session is read the rows stay editable; the server refuses a change without the scope.
  const hasCredentials = session.data === undefined || session.data.scopes.includes("credentials");

  return (
    <>
      {ROWS.map((row) => {
        const field = saved[row.key];
        const apply = (value: string | number | null, done: () => void) => save.mutate({ [row.key]: value }, { onSuccess: done });
        return (
          <SettingRow
            key={row.key}
            label={field.label}
            value={String(field.value)}
            source={field.source}
            readOnlyReason={readOnlyReason(field, row, hasCredentials)}
            inputType={row.inputType}
            min={field.min}
            max={field.max}
            pending={save.isPending}
            error={save.isError && save.variables !== undefined && row.key in save.variables ? save.error : null}
            onSave={(text, done) => apply(row.inputType === "number" ? Number(text) : text, done)}
            onClear={(done) => apply(null, done)}
            onRetry={() => save.reset()}
          />
        );
      })}
      <p className="text-meta text-muted-foreground">
        Idle sleep: the server frees the model after this many idle seconds and loads it again on the next request, so that answer is slower. 0 turns sleep off.
      </p>
    </>
  );
}
