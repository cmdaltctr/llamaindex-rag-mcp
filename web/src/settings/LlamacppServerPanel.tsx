import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { useLlamacppServer, useRestartLlamacppServer, useStartLlamacppServer, useStopLlamacppServer } from "../api/llamacppServerHooks";
import { LlamacppServerFields } from "./LlamacppServerFields";
import { statusLine } from "./llamacppServerWords";

/** The "Local server" block of the llama.cpp card: settings, state and Start, Stop and Restart. */
export function LlamacppServerPanel() {
  const query = useLlamacppServer();
  const start = useStartLlamacppServer();
  const stop = useStopLlamacppServer();
  const restart = useRestartLlamacppServer();
  const status = query.data;

  if (status === undefined) {
    return query.isError ? <ErrorNotice error={query.error} onRetry={() => void query.refetch()} /> : null;
  }
  const busy = start.isPending || stop.isPending || restart.isPending;
  const live = status.state === "starting" || status.state === "running";
  const failure = [start, stop, restart].find((mutation) => mutation.isError);

  return (
    <div role="group" aria-labelledby="llamacpp-server-title" className="flex flex-col gap-2 border-t border-border pt-3">
      <h4 id="llamacpp-server-title" className="text-ui font-semibold">
        Local server
      </h4>
      <p className="text-meta text-muted-foreground">omrg starts and stops only this server. It never touches a server you started yourself.</p>
      <LlamacppServerFields saved={status.saved} />
      <div role="status" className="text-ui">
        {statusLine(status)}
      </div>
      {live && status.pending_restart ? <p className="text-meta text-muted-foreground">Restart to apply the saved values.</p> : null}
      <div className="flex flex-wrap items-center gap-2">
        {live ? null : (
          <Button size="sm" disabled={busy} onClick={() => start.mutate()}>
            Start
          </Button>
        )}
        {live ? (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => stop.mutate()}>
            Stop
          </Button>
        ) : null}
        {status.state === "running" ? (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => restart.mutate()}>
            Restart
          </Button>
        ) : null}
      </div>
      {failure !== undefined ? <ErrorNotice error={failure.error} onRetry={() => failure.reset()} /> : null}
    </div>
  );
}
