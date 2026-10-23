import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { CardInset } from "../components/ui/card";
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
    <div role="group" aria-labelledby="llamacpp-server-title" className="flex flex-col gap-2">
      <h4 id="llamacpp-server-title" className="text-ui font-semibold">
        Local server
      </h4>
      <p className="text-meta text-muted-foreground">omrs starts and stops only this server. It never touches a server you started yourself.</p>
      <LlamacppServerFields saved={status.saved} />
      <CardInset>
        <div role="status" className="text-ui">
          {statusLine(status)}
        </div>
        {live && status.pending_restart ? <p className="text-meta text-muted-foreground">Restart to apply</p> : null}
        <p className="text-meta text-muted-foreground">The embedding server is not managed here.</p>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={busy || live} onClick={() => start.mutate()}>
            Start
          </Button>
          <Button size="sm" variant="outline" disabled={busy || !live} onClick={() => stop.mutate()}>
            Stop
          </Button>
          <Button size="sm" variant="outline" disabled={busy || status.state !== "running"} onClick={() => restart.mutate()}>
            Restart
          </Button>
        </div>
      </CardInset>
      {failure !== undefined ? <ErrorNotice error={failure.error} onRetry={() => failure.reset()} /> : null}
    </div>
  );
}
