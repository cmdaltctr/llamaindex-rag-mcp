import { TriangleAlert } from "lucide-react";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import type { Integration, IntegrationAvailability, InstallType } from "../api/integrations";
import { CopyCommand } from "./CopyCommand";
import { InstallControls, installPhase } from "./InstallControls";
import type { InstallControl } from "./useIntegrationInstall";

const STATUS: Record<IntegrationAvailability, { label: string; variant: "success" | "neutral" | "warning" | "info" }> = {
  available: { label: "Installed", variant: "success" },
  "not-installed": { label: "Not installed", variant: "neutral" },
  unknown: { label: "Unknown", variant: "warning" },
  "restart-needed": { label: "Installed, restart to use", variant: "info" },
};

/** A red callout with the entry's install caution. It shows only while the entry is not installed yet. */
function InstallCaution({ text }: { text: string }) {
  return (
    <div data-slot="install-caution" className="flex min-w-0 gap-2 rounded-panel border border-status-error bg-status-error/10 px-3 py-2">
      <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-status-error-label" />
      <p className="min-w-0 text-ui text-status-error-label [overflow-wrap:anywhere]">
        <strong>Before you install: </strong>
        {text}
      </p>
    </div>
  );
}

/** The DOM id of an entry's card, so a link such as `#/integrations/anthropic` can focus it. */
export function integrationCardId(id: string): string {
  return `integration-${id}`;
}

interface IntegrationCardProps {
  integration: Integration;
  installType: InstallType;
  control: InstallControl;
}

/** One catalogue entry: name, status badge with its value as text, purpose, Install action and install command. */
export function IntegrationCard({ integration, installType, control }: IntegrationCardProps) {
  // An install that succeeded in this launch shows as restart-needed before the catalogue is read again.
  const phase = installPhase(integration, control);
  const status = STATUS[phase === "restart" ? "restart-needed" : integration.availability];
  const caution = integration.install_caution !== null && phase !== "restart" && (integration.availability === "not-installed" || integration.availability === "unknown");
  return (
    <Card id={integrationCardId(integration.id)} tabIndex={-1} className="scroll-mt-4">
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
        {caution && <InstallCaution text={integration.install_caution ?? ""} />}
        <InstallControls integration={integration} control={control} />
        {integration.install_command === null ? (
          <p className="text-meta text-muted-foreground">Always on. Nothing to install.</p>
        ) : (
          <>
            <CopyCommand command={integration.install_command} subject={integration.name} />
            {installType === "uv-tool" && (
              <p className="text-meta text-muted-foreground">This command keeps the extra after a later reinstall.</p>
            )}
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
