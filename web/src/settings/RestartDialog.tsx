import { useMutation, useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { ApiError } from "../api/client";
import { postPower } from "../api/power";
import { powerQuery } from "../api/queries";
import { AlertNotice } from "../components/AlertNotice";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { useReturnFocus } from "../studio/useReturnFocus";

/** Starts the server again in a terminal. A server run by hand has no login item to restart. */
const TERMINAL_COMMAND = "omrg web";

function Command({ children }: { children: string }) {
  return <code className="rounded-small border border-border bg-muted px-1.5 py-0.5 text-code">{children}</code>;
}

export interface RestartDialogProps {
  /** What needs the restart, as text such as "Port 9100". `null` keeps the dialog closed. */
  change: string | null;
  /** True when `change` names several settings, so the sentence says "apply". */
  plural?: boolean;
  /** Called on "Later", on Escape and on Close. The row stays marked "Restart to apply". */
  onLater: () => void;
}

/**
 * Asks the person to restart after a setting that applies only after a
 * restart. "Restart now" posts the power menu restart. When the server runs in
 * a terminal, or the power route does not answer, the dialog shows the command
 * instead, because the page cannot restart that server.
 */
export function RestartDialog({ change, plural = false, onLater }: RestartDialogProps) {
  const api = useApi();
  const returnFocus = useReturnFocus();
  const open = change !== null;
  const power = useQuery({ ...powerQuery(api), enabled: open });
  const restart = useMutation({ mutationFn: () => postPower(api, "restart") });
  const managed = power.data?.managed === true;
  const terminal = power.data?.managed === false || power.isError;
  const busy = restart.error instanceof ApiError && restart.error.status === 409;

  function later() {
    restart.reset();
    onLater();
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : later())}>
      <DialogContent {...returnFocus}>
        <DialogHeader>
          <DialogTitle>Restart to apply?</DialogTitle>
          <DialogDescription>{`${change ?? ""} ${plural ? "apply" : "applies"} after a restart.`}</DialogDescription>
        </DialogHeader>
        {restart.isSuccess ? (
          <p className="text-ui">
            {"Restarting. This page signs in again by itself when OMRG is back. If the port changed, run "}
            <Command>omrg web open</Command>
            {" in a terminal."}
          </p>
        ) : null}
        {terminal && !restart.isSuccess ? (
          <p className="text-ui">
            {"This server runs in a terminal, so this page cannot restart it. Stop it there with Ctrl+C, then run "}
            <Command>{TERMINAL_COMMAND}</Command>
            {" again."}
          </p>
        ) : null}
        {restart.isError && busy ? (
          <AlertNotice message="OMRG is busy with a run or an ingestion, so nothing changed. Try again when it has finished.">
            <Button variant="outline" onClick={() => restart.mutate()}>
              Retry
            </Button>
          </AlertNotice>
        ) : null}
        {restart.isError && !busy ? <ErrorNotice error={restart.error} onRetry={() => restart.mutate()} /> : null}
        <DialogFooter>
          {restart.isSuccess ? (
            <Button type="button" variant="outline" onClick={later}>
              Close
            </Button>
          ) : (
            <>
              <Button type="button" variant="outline" onClick={later}>
                Later
              </Button>
              {terminal ? null : (
                <Button type="button" disabled={!managed || restart.isPending} onClick={() => restart.mutate()}>
                  Restart now
                </Button>
              )}
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
