import { useMemo } from "react";
import { ApiError } from "../api/client";
import { AlertNotice } from "../components/AlertNotice";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";

type RefusalAction = "retry" | "check";

/** One line and one action for each `reason` of a refused install (409). */
const REFUSALS: Record<string, { message: string; action: RefusalAction }> = {
  "install-running": { message: "Another install is running. Wait for it to finish, then try again.", action: "retry" },
  "not-installable-here": { message: "This integration cannot be installed from the app. Run its command instead.", action: "check" },
  "not-uv-tool": { message: "This server was not installed with uv tool, so it cannot install from the app. Run the command instead.", action: "check" },
  "uv-not-found": { message: "The server cannot find uv, so it cannot install from the app. Run the command instead.", action: "check" },
  "already-installed": { message: "This integration is already installed. Restart the server to use it.", action: "check" },
  "no-requirements": { message: "This integration adds no packages, so there is nothing to install.", action: "check" },
};

/** The `reason` of a 409 install refusal, or `null` for any other failure. */
function refusalReason(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.kind !== "http" || error.status !== 409) return null;
  const body = error.body;
  if (typeof body !== "object" || body === null) return null;
  const reason = (body as Record<string, unknown>).reason;
  return typeof reason === "string" ? reason : null;
}

interface InstallRefusalProps {
  error: unknown;
  /** Sends the install again. */
  onRetry: () => void;
  /** Reads the catalogue again, so the entry shows what the server can do now. */
  onCheck: () => void;
}

/**
 * A refused install as one friendly line and one action. A known 409 reason
 * gets its own line; anything else falls back to `describeError`. The raw
 * message goes to the console only.
 */
export function InstallRefusal({ error, onRetry, onCheck }: InstallRefusalProps) {
  const known = useMemo(() => {
    const reason = refusalReason(error);
    const refusal = reason === null ? undefined : REFUSALS[reason];
    if (refusal !== undefined) console.error(error instanceof Error ? error.message : String(error), error);
    return refusal;
  }, [error]);

  if (known === undefined) return <ErrorNotice error={error} onRetry={onRetry} />;
  return (
    <AlertNotice message={known.message}>
      {known.action === "retry" ? (
        <Button type="button" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      ) : (
        <Button type="button" variant="outline" onClick={onCheck}>
          Check again
        </Button>
      )}
    </AlertNotice>
  );
}
