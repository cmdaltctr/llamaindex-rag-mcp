import { Badge } from "../components/ui/badge";

type Variant = "neutral" | "info" | "success" | "error" | "warning";

const RUN_VARIANT: Record<string, Variant> = {
  queued: "neutral",
  running: "info",
  cancelling: "warning",
  succeeded: "success",
  failed: "error",
  cancelled: "warning",
  interrupted: "warning",
};

/** A run status as a badge. The status word is always the text, so colour never carries it alone. */
export function RunStatusBadge({ status }: { status: string }) {
  return <Badge variant={RUN_VARIANT[status] ?? "neutral"}>{status}</Badge>;
}
