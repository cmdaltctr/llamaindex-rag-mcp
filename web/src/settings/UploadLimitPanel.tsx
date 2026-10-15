import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useApi } from "../api/ApiProvider";
import { uploadLimitQuery } from "../api/queries";
import type { UploadLimitState } from "../api/settings";
import { useSetUploadLimit } from "../api/settingsMutations";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { formatMiB } from "../lib/uploadLimit";

function sourceLine(state: UploadLimitState): string {
  if (state.saved_mib === null) return `No limit is saved, so the default of ${state.default_mib} MiB applies.`;
  return `Saved limit: ${state.saved_mib} MiB.`;
}

/** The form for a saved limit. The range comes from the server response, never from a copy in the client. */
function LimitForm({ state }: { state: UploadLimitState }) {
  const save = useSetUploadLimit();
  const [text, setText] = useState("");
  const [invalid, setInvalid] = useState(false);
  const rangeError = `Enter a whole number from ${state.min_mib} to ${state.max_mib}.`;

  function submit(event: FormEvent) {
    event.preventDefault();
    const mib = /^\d+$/.test(text.trim()) ? Number(text.trim()) : Number.NaN;
    if (!Number.isInteger(mib) || mib < state.min_mib || mib > state.max_mib) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    save.mutate(mib, { onSuccess: () => setText("") });
  }

  return (
    <>
      <form onSubmit={submit} noValidate className="flex flex-col gap-2">
        <Label htmlFor="upload-limit-input">Limit per file, in MiB</Label>
        <div className="flex flex-wrap items-start gap-2">
          <Input
            id="upload-limit-input"
            type="number"
            inputMode="numeric"
            className="w-32"
            value={text}
            aria-invalid={invalid}
            aria-describedby={invalid ? "upload-limit-error" : "upload-limit-range"}
            onChange={(event) => setText(event.target.value)}
          />
          <Button type="submit" disabled={save.isPending}>
            Save limit
          </Button>
          {state.saved_mib !== null ? (
            <Button type="button" variant="outline" disabled={save.isPending} onClick={() => save.mutate(null)}>
              {`Use the default (${state.default_mib} MiB)`}
            </Button>
          ) : null}
        </div>
        {invalid ? (
          <p id="upload-limit-error" className="text-meta text-status-error-label">
            {rangeError}
          </p>
        ) : (
          <p id="upload-limit-range" className="text-meta text-muted-foreground">
            {`Allowed: ${state.min_mib} to ${state.max_mib} MiB.`}
          </p>
        )}
      </form>
      {save.isError ? <ErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
    </>
  );
}

/** The per-file upload limit. A launch option locks it for this server run, so the form is not shown then. */
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
              <LimitForm state={state} />
            </>
          )}
        </>
      )}
    </Card>
  );
}
