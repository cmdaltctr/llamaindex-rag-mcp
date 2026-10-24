import { Download, LoaderCircle, RotateCcw } from "lucide-react";
import { useState } from "react";
import type { Integration, IntegrationInstall } from "../api/integrations";
import { AlertNotice } from "../components/AlertNotice";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { RestartDialog } from "../settings/RestartDialog";
import { useReturnFocus } from "../studio/useReturnFocus";
import { InstallRefusal } from "./InstallRefusal";
import type { InstallControl } from "./useIntegrationInstall";

/** The output block keeps the last lines the server sends, which is at most 40. */
const OUTPUT_LINES = 40;

const FAILURE: Record<NonNullable<IntegrationInstall["reason"]>, string> = {
  "exit-code": "The install failed. The last output lines are below.",
  "check-failed": "The packages were installed, but they clash with packages the server already has. Do not restart yet: run the command below to reinstall cleanly.",
  "timed-out": "The install stopped after 10 minutes. The last output lines are below.",
  "start-failed": "The install could not start.",
};

/** The phase of one entry, from the catalogue and the install state of this launch. */
export function installPhase(integration: Integration, control: InstallControl): "restart" | "running" | "failed" | "ready" | "none" {
  const extra = integration.extra;
  const install = control.install;
  const mine = extra !== null && install?.extra === extra;
  // A local success only lifts an entry the catalogue still calls not installed. After a restart the
  // catalogue says available, and the cached status must not hide that.
  const succeeded = mine && install?.state === "succeeded" && integration.availability === "not-installed";
  if (integration.availability === "restart-needed" || succeeded) return "restart";
  if ((mine && install?.state === "running") || (extra !== null && control.starting === extra)) return "running";
  if (mine && install?.state === "failed") return "failed";
  return integration.installable && extra !== null ? "ready" : "none";
}

function InstallDialog({ integration, open, onCancel, onConfirm }: { integration: Integration; open: boolean; onCancel: () => void; onConfirm: () => void }) {
  const returnFocus = useReturnFocus();
  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onCancel())}>
      <DialogContent {...returnFocus}>
        <DialogHeader>
          <DialogTitle>{`Install ${integration.name}?`}</DialogTitle>
          <DialogDescription>
            {"This adds the "}
            <code className="text-code">{integration.extra}</code>
            {" extra to the server. The server needs a restart before you can use it."}
          </DialogDescription>
        </DialogHeader>
        {integration.packages.length > 0 ? (
          <div className="flex min-w-0 flex-col gap-1 text-ui">
            <p>It adds these packages:</p>
            <ul aria-label="Packages" className="flex flex-col gap-1">
              {integration.packages.map((name) => (
                <li key={name}>
                  <code dir="ltr" className="text-code [overflow-wrap:anywhere]">
                    {name}
                  </code>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" onClick={onConfirm}>
            Install
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FailedInstall({ integration, install, control }: { integration: Integration; install: IntegrationInstall; control: InstallControl }) {
  const extra = integration.extra ?? "";
  const output = install.output.slice(-OUTPUT_LINES);
  // A second install cannot mend a clash; the lasting command rebuilds the environment.
  const retry = install.reason !== "check-failed";
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <AlertNotice message={FAILURE[install.reason ?? "exit-code"]}>
        {retry ? (
          <Button type="button" variant="outline" size="sm" disabled={control.busy} onClick={() => control.start(extra)}>
            <RotateCcw aria-hidden="true" />
            Retry
          </Button>
        ) : null}
      </AlertNotice>
      {output.length > 0 ? (
        <pre
          dir="ltr"
          tabIndex={0}
          aria-label={`Install output for ${integration.name}`}
          className="max-h-64 min-w-0 max-w-full overflow-auto rounded-small border border-border bg-muted px-2 py-1.5 text-code"
        >
          {output.join("\n")}
        </pre>
      ) : null}
    </div>
  );
}

/** The Install button, its confirm dialog, the progress line, the failure output and the Restart action of one entry. */
export function InstallControls({ integration, control }: { integration: Integration; control: InstallControl }) {
  const [confirming, setConfirming] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const phase = installPhase(integration, control);
  const extra = integration.extra ?? "";
  const refusal = control.refusal(extra);

  if (phase === "none") return null;
  if (phase === "restart") {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-meta text-muted-foreground">Restart the server to use it.</p>
        <Button type="button" variant="outline" size="sm" onClick={() => setRestarting(true)}>
          Restart
        </Button>
        <RestartDialog change={restarting ? integration.name : null} onLater={() => setRestarting(false)} />
      </div>
    );
  }
  if (phase === "running") {
    return (
      <p role="status" className="flex items-center gap-2 text-ui">
        <LoaderCircle aria-hidden="true" className="size-4 shrink-0 motion-safe:animate-spin" />
        <span className="min-w-0 [overflow-wrap:anywhere]">{`Installing ${extra}. This can take a few minutes.`}</span>
      </p>
    );
  }
  if (phase === "failed" && control.install !== undefined) {
    return (
      <>
        <FailedInstall integration={integration} install={control.install} control={control} />
        {refusal !== null ? <InstallRefusal error={refusal} onRetry={() => control.start(extra)} onCheck={control.recheck} /> : null}
      </>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div>
        <Button type="button" size="sm" aria-label={`Install ${integration.name}`} disabled={control.busy} onClick={() => setConfirming(true)}>
          <Download aria-hidden="true" />
          Install
        </Button>
      </div>
      {refusal !== null ? <InstallRefusal error={refusal} onRetry={() => control.start(extra)} onCheck={control.recheck} /> : null}
      <InstallDialog
        integration={integration}
        open={confirming}
        onCancel={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          control.start(extra);
        }}
      />
    </div>
  );
}
