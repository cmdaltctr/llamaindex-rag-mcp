import { useMutation, useQuery } from "@tanstack/react-query";
import { Power, RotateCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useApi } from "../api/ApiProvider";
import { ApiError } from "../api/client";
import { postPower, type PowerAction } from "../api/power";
import { healthQuery, powerQuery } from "../api/queries";
import { useReturnFocus } from "../studio/useReturnFocus";
import { CopyButton } from "../settings/CopyButton";
import { AlertNotice } from "./AlertNotice";
import { ErrorNotice } from "./ErrorNotice";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "./ui/dialog";
import { Popover } from "./ui/popover";

const HEALTH_POLL_MS = 15_000;
/** After a 202 the server ends within a second, so a health poll in this window would only fail. */
const QUIET_MS = 5_000;
const COMMANDS = [
  { what: "restart command", command: "omrg web restart", hint: "Restart the login item." },
  { what: "open command", command: "omrg web open", hint: "Open the workspace in the browser with a fresh link." },
] as const;

const COPY: Record<PowerAction, { label: string; title: string; ask: string; command: string; done: string; next: string }> = {
  off: {
    label: "Turn off",
    title: "Turn off OMRG?",
    ask: "OMRG stops. It stays off until you log in again or run",
    command: "omrg web start",
    done: "Turned off. Run",
    next: "in a terminal to turn it on.",
  },
  restart: {
    label: "Restart",
    title: "Restart OMRG?",
    ask: "OMRG restarts. This page signs in again by itself when it is back. If it does not, run",
    command: "omrg web open",
    done: "Restarting. This page signs in again by itself when OMRG is back. If it does not, run",
    next: "in a terminal.",
  },
};

function Command({ children }: { children: string }) {
  return <code className="rounded-small border border-border bg-muted px-1.5 py-0.5 text-code">{children}</code>;
}

/** The sentence after a 202, with the command to run next. */
function Done({ action }: { action: PowerAction }) {
  const { done, command, next } = COPY[action];
  return (
    <p className="text-ui">
      {`${done} `}
      <Command>{command}</Command>
      {` ${next}`}
    </p>
  );
}

function isBusy(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}

/** Why the buttons are off, in one line. `null` while they are on. */
function disabledReason(managed: boolean | undefined, failed: boolean, pending: boolean): string | null {
  if (managed === true) return null;
  if (managed === false) return "This server runs in a terminal, so this page cannot turn it off or restart it. Use these commands there.";
  if (failed) return "This page cannot tell whether it may control the server. Use these commands in a terminal.";
  return pending ? "Checking whether this page may control the server." : null;
}

/**
 * The power light and panel at the foot of the navigation. The light follows
 * `GET /v1/health`. Turn off and Restart each open a confirmation before the
 * page posts to `/v1/server/power`, and both stay disabled unless that route
 * says the server is the login item. The dialog sits beside the panel, not
 * inside it, because the panel closes on any click outside it.
 */
export function PowerMenu() {
  const api = useApi();
  const [quiet, setQuiet] = useState(false);
  const [asking, setAsking] = useState<PowerAction | null>(null);
  const [done, setDone] = useState<PowerAction | null>(null);
  const returnFocus = useReturnFocus();

  const health = useQuery({ ...healthQuery(api), refetchInterval: quiet ? false : HEALTH_POLL_MS });
  const power = useQuery(powerQuery(api));
  const act = useMutation({ mutationFn: (action: PowerAction) => postPower(api, action) });

  useEffect(() => {
    if (!quiet) return;
    const timer = setTimeout(() => setQuiet(false), QUIET_MS);
    return () => clearTimeout(timer);
  }, [quiet]);

  // A failed poll keeps the earlier `data`, so the error wins over it.
  const state = health.isError ? "Not answering" : health.data ? "Running" : "Checking";
  const running = state === "Running";
  const reason = done === null ? disabledReason(power.data?.managed, power.isError, power.isPending) : null;
  const canAct = power.data?.managed === true && done === null;

  async function confirm() {
    if (asking === null) return;
    try {
      await act.mutateAsync(asking);
    } catch {
      return;
    }
    setDone(asking);
    setQuiet(true);
  }

  function change(next: boolean) {
    if (next) return;
    act.reset();
    setAsking(null);
  }

  const asked = asking === null ? null : COPY[asking];
  const finished = act.isSuccess && asking !== null;

  return (
    <>
      <Popover
        slot="power-panel"
        placement="above"
        width={272}
        trigger={(props) => (
          <Button variant="ghost" size="icon" aria-label={`Server status: ${state}`} {...props}>
            <Power aria-hidden="true" className={running ? "text-status-success" : "text-muted-foreground"} />
          </Button>
        )}
      >
        <p className="text-ui font-medium">{state}</p>
        {running && health.data ? <p className="text-muted-foreground">{`OMRG version ${health.data.version}`}</p> : null}
        {done !== null ? <Done action={done} /> : null}
        <div className="flex flex-wrap gap-2">
          <Button variant="destructive" size="sm" disabled={!canAct} onClick={() => setAsking("off")}>
            <Power aria-hidden="true" />
            Turn off
          </Button>
          <Button variant="outline" size="sm" disabled={!canAct} onClick={() => setAsking("restart")}>
            <RotateCw aria-hidden="true" />
            Restart
          </Button>
        </div>
        {reason !== null ? <p className="text-muted-foreground">{reason}</p> : null}
        {!canAct && done === null
          ? COMMANDS.map(({ what, command, hint }) => (
              <div key={command} className="flex flex-col gap-1">
                <span className="text-muted-foreground">{hint}</span>
                <code className="select-all rounded-small border border-border bg-muted px-2 py-1.5 text-code [overflow-wrap:anywhere]">{command}</code>
                <CopyButton text={command} what={what} />
              </div>
            ))
          : null}
      </Popover>
      <Dialog open={asking !== null} onOpenChange={change}>
        <DialogContent {...returnFocus}>
          <DialogHeader>
            <DialogTitle>{asked?.title ?? ""}</DialogTitle>
            {asked !== null && !finished ? (
              <DialogDescription>
                {`${asked.ask} `}
                <Command>{asked.command}</Command>
                {" in a terminal."}
              </DialogDescription>
            ) : null}
          </DialogHeader>
          {finished && asking !== null ? <Done action={asking} /> : null}
          {act.isError && isBusy(act.error) ? (
            <AlertNotice message="OMRG is busy with a run or an ingestion, so nothing changed. Try again when it has finished.">
              <Button variant="outline" onClick={() => void confirm()}>
                Retry
              </Button>
            </AlertNotice>
          ) : null}
          {act.isError && !isBusy(act.error) ? <ErrorNotice error={act.error} onRetry={() => void confirm()} /> : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => change(false)}>
              {finished ? "Close" : "Cancel"}
            </Button>
            {finished ? null : (
              <Button type="button" variant={asking === "off" ? "destructive" : "default"} disabled={act.isPending} onClick={() => void confirm()}>
                {asked?.label}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
