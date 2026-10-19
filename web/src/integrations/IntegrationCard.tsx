import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import type { Integration, IntegrationAvailability } from "../api/integrations";
import { CopyCommand } from "./CopyCommand";

const STATUS: Record<IntegrationAvailability, { label: string; variant: "success" | "neutral" | "warning" }> = {
  available: { label: "Available", variant: "success" },
  "not-installed": { label: "Not installed", variant: "neutral" },
  unknown: { label: "Unknown", variant: "warning" },
};

/** One catalogue entry: name, status badge with its value as text, purpose and install command. */
export function IntegrationCard({ integration }: { integration: Integration }) {
  const status = STATUS[integration.availability];
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <CardTitle className="min-w-0 break-words">{integration.name}</CardTitle>
          <Badge variant={status.variant}>{status.label}</Badge>
        </div>
        <CardDescription>{integration.purpose}</CardDescription>
      </CardHeader>
      <CardContent>
        {integration.availability === "unknown" && (
          <p className="text-meta text-muted-foreground">The server could not check this integration.</p>
        )}
        {integration.install_command === null ? (
          <p className="text-meta text-muted-foreground">Always on. Nothing to install.</p>
        ) : (
          <>
            <CopyCommand command={integration.install_command} subject={integration.name} />
            {integration.pip_command !== null && (
              <p className="text-meta text-muted-foreground">
                With pip: <code className="text-code [overflow-wrap:anywhere]">{integration.pip_command}</code>
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
