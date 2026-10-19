import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { uploadLimitQuery } from "../api/queries";
import type { UploadLimitState } from "../api/settings";
import { useSetUploadLimit } from "../api/settingsMutations";
import { ErrorNotice } from "../components/ErrorNotice";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { formatMiB } from "../lib/uploadLimit";
import { SettingRow } from "./SettingRow";
import { wholeNumberIn } from "./validation";

const MIB = 1024 * 1024;

function sourceLine(state: UploadLimitState): string {
  if (state.saved_mib === null) return `No limit is saved, so the default of ${state.default_mib} MiB applies.`;
  return `Saved limit: ${state.saved_mib} MiB.`;
}

/** The row for the limit. The range comes from the server response, never from a copy in the client. */
function LimitRow({ state }: { state: UploadLimitState }) {
  const save = useSetUploadLimit();
  const message = `Enter a whole number from ${state.min_mib} to ${state.max_mib}.`;

  return (
    <>
      <SettingRow
        label="Limit per file, in MiB"
        value={String(Math.round(state.max_bytes / MIB))}
        source={state.source}
        inputType="number"
        min={state.min_mib}
        max={state.max_mib}
        validate={wholeNumberIn(state.min_mib, state.max_mib, message)}
        pending={save.isPending}
        error={save.isError ? save.error : null}
        onSave={(text, done) => save.mutate(Number(text), { onSuccess: done })}
        onClear={(done) => save.mutate(null, { onSuccess: done })}
        onRetry={() => save.reset()}
      />
      <p className="text-meta text-muted-foreground">{`Allowed: ${state.min_mib} to ${state.max_mib} MiB.`}</p>
    </>
  );
}

/** The per-file upload limit. A launch option locks it for this server run, so no row is shown then. */
export function UploadLimitPanel() {
  const query = useQuery(uploadLimitQuery(useApi()));
  const state = query.data;

  return (
    <Card role="region" aria-labelledby="upload-limit-title">
      <CardHeader>
        <CardTitle id="upload-limit-title">Upload limit</CardTitle>
      </CardHeader>
      {state === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading.
          </p>
        )
      ) : (
        <>
          <p className="text-ui">{`The limit in force is ${formatMiB(state.max_bytes)} per file.`}</p>
          {state.source === "launch" ? (
            <p className="text-ui">
              The limit was set when the server started. To change it here, remove <code className="font-mono text-code">--max-upload-mib</code> or{" "}
              <code className="font-mono text-code">WEB_MAX_UPLOAD_MIB</code> and restart the server.
            </p>
          ) : (
            <>
              <p className="text-ui">{sourceLine(state)}</p>
              <p className="text-meta text-muted-foreground">A change applies to new uploads straight away. An upload that has already started keeps its limit.</p>
              <LimitRow state={state} />
            </>
          )}
        </>
      )}
    </Card>
  );
}
