import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useApi } from "../api/ApiProvider";
import { webPortQuery } from "../api/queries";
import { useSetWebPort } from "../api/settingsMutations";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

const MIN_PORT = 1024;
const MAX_PORT = 65535;
const PORT_ERROR = `Enter a whole number from ${MIN_PORT} to ${MAX_PORT}.`;

/** The port saved for later launches. The running server never rebinds. */
export function WebPortPanel() {
  const query = useQuery(webPortQuery(useApi()));
  const save = useSetWebPort();
  const [text, setText] = useState("");
  const [invalid, setInvalid] = useState(false);
  const state = query.data;

  function submit(event: FormEvent) {
    event.preventDefault();
    const port = /^\d+$/.test(text.trim()) ? Number(text.trim()) : Number.NaN;
    if (!Number.isInteger(port) || port < MIN_PORT || port > MAX_PORT) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    save.mutate(port, { onSuccess: () => setText("") });
  }

  return (
    <Card role="region" aria-labelledby="mcp-port-title">
      <CardHeader>
        <CardTitle id="mcp-port-title">Web port</CardTitle>
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
          <p className="text-ui">This server listens on port {state.bound}.</p>
          <p className="text-ui">{state.saved === null ? "No port is saved. The next launch uses --port, or 8765." : `Saved port: ${state.saved}.`}</p>
          <p className="text-meta text-muted-foreground">
            A saved port applies on the next launch. The running server still listens on port {state.bound} until you restart it.
          </p>
          <form onSubmit={submit} noValidate className="flex flex-col gap-2">
            <Label htmlFor="web-port-input">Port for the next launch</Label>
            <div className="flex flex-wrap items-start gap-2">
              <Input
                id="web-port-input"
                type="number"
                inputMode="numeric"
                className="w-32"
                value={text}
                aria-invalid={invalid}
                aria-describedby={invalid ? "web-port-error" : undefined}
                onChange={(event) => setText(event.target.value)}
              />
              <Button type="submit" disabled={save.isPending}>
                Save port
              </Button>
              {state.saved !== null ? (
                <Button variant="outline" disabled={save.isPending} onClick={() => save.mutate(null)}>
                  Clear saved port
                </Button>
              ) : null}
            </div>
            {invalid ? (
              <p id="web-port-error" className="text-meta text-status-error-label">
                {PORT_ERROR}
              </p>
            ) : null}
          </form>
          {save.isError ? <ErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
        </>
      )}
    </Card>
  );
}
