import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useApi } from "../api/ApiProvider";
import { webPortQuery } from "../api/queries";
import type { WebPortState } from "../api/settings";
import { useSetWebPort } from "../api/settingsMutations";
import { ErrorNotice } from "../components/ErrorNotice";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { RestartDialog } from "./RestartDialog";
import { SettingRow } from "./SettingRow";
import { wholeNumberIn } from "./validation";

const MIN_PORT = 1024;
const MAX_PORT = 65535;
const DEFAULT_PORT = 8765;
const PORT_ERROR = `Enter a whole number from ${MIN_PORT} to ${MAX_PORT}.`;

/** The port saved for later launches. The running server never rebinds, so a saved port that differs from the bound one waits for a restart. */
export function WebPortPanel() {
  const query = useQuery(webPortQuery(useApi()));
  const save = useSetWebPort();
  const [restart, setRestart] = useState<string | null>(null);
  const state = query.data;

  function saved(next: WebPortState, done: () => void) {
    done();
    if (next.saved !== null && next.saved !== next.bound) setRestart(`Port ${next.saved}`);
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
          {state.saved === null ? <p className="text-ui">{`No port is saved. The next launch uses --port, or ${DEFAULT_PORT}.`}</p> : null}
          {state.saved !== null && state.saved !== state.bound ? <p className="text-ui">Restart to apply</p> : null}
          <p className="text-meta text-muted-foreground">
            A saved port applies on the next launch. The running server still listens on port {state.bound} until you restart it.
          </p>
          <SettingRow
            label="Port for the next launch"
            value={String(state.saved ?? DEFAULT_PORT)}
            source={state.saved === null ? "default" : "config-file"}
            inputType="number"
            min={MIN_PORT}
            max={MAX_PORT}
            validate={wholeNumberIn(MIN_PORT, MAX_PORT, PORT_ERROR)}
            pending={save.isPending}
            error={save.isError ? save.error : null}
            onSave={(text, done) => save.mutate(Number(text), { onSuccess: (next) => saved(next, done) })}
            onClear={(done) => save.mutate(null, { onSuccess: (next) => saved(next, done) })}
            onRetry={() => save.reset()}
          />
        </>
      )}
      <RestartDialog change={restart} onLater={() => setRestart(null)} />
    </Card>
  );
}
