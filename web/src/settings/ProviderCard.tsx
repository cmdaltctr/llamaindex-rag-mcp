import { useState } from "react";
import type { Connection, ProviderField } from "../api/settings";
import { Badge } from "../components/ui/badge";
import { Card, CardHeader, CardInset, CardTitle } from "../components/ui/card";
import { isLoopback, ROLE_NAMES } from "./connectionWords";
import { IntegrationLink } from "./IntegrationLink";
import { PROVIDER_EXTRAS } from "./providerExtras";
import { ProviderKeyField } from "./ProviderKeyField";
import { ProviderTest } from "./ProviderTest";
import { ProviderValueField } from "./ProviderValueField";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";

interface ProviderCardProps {
  connection: Connection;
  keychain: "available" | "unavailable";
  /** The folder whose `.env` the server read. */
  configDir: string;
}

/** The address a field would use if the user saved the typed text now. */
function addressInUse(field: ProviderField, typed: Record<string, string>): string | null {
  return field.kind === "url" ? (typed[field.id] ?? String(field.value ?? "")) : null;
}

/** One provider: badges, roles, editable fields, read-only values, notices and a Test action. */
export function ProviderCard({ connection, keychain, configDir }: ProviderCardProps) {
  const titleId = `provider-${connection.provider}`;
  const ProviderExtra = PROVIDER_EXTRAS[connection.provider];
  const [typed, setTyped] = useState<Record<string, string>>({});
  const setValue = (id: string, value: string | null) =>
    setTyped((current) => {
      const next = { ...current };
      if (value === null) delete next[id];
      else next[id] = value;
      return next;
    });
  const offMachine =
    connection.locality === "cloud" || connection.fields.some((field) => {
      const address = addressInUse(field, typed);
      return address !== null && address !== "" && !isLoopback(address);
    });

  const body = (
    <>
      {!connection.installed ? (
        <p className="text-ui">
          {"Not installed. "}
          <IntegrationLink connection={connection} />
          {"."}
        </p>
      ) : null}
      {connection.fields.map((field) =>
        field.kind === "secret" ? (
          <ProviderKeyField key={field.id} provider={connection.provider} field={field} keychain={keychain} onTyped={(text) => setValue(field.id, text === "" ? null : text)} />
        ) : (
          <ProviderValueField key={field.id} provider={connection.provider} field={field} configDir={configDir} onTyped={(text) => setValue(field.id, text)} />
        ),
      )}
      {connection.read_only.length > 0 ? (
        <CardInset>
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-ui">
            {connection.read_only.map((entry) => (
              <div key={entry.label} className="col-span-2 grid grid-cols-subgrid">
                <dt className="text-meta text-muted-foreground">
                  {entry.label} <span>(Read-only)</span>
                </dt>
                <dd>
                  <code dir="ltr" className={CODE}>
                    {entry.value}
                  </code>
                </dd>
              </div>
            ))}
          </dl>
        </CardInset>
      ) : null}
      {offMachine ? (
        <p className="text-meta text-muted-foreground">
          {connection.locality === "cloud" ? "Text you send to this provider leaves this machine." : "This address is not on this machine, so text sent to it leaves this machine."}
        </p>
      ) : null}
      <ProviderTest provider={connection.provider} typed={typed} cloud={connection.locality === "cloud"} />
    </>
  );

  const header = (
    <CardHeader>
      <CardTitle id={titleId}>{connection.display_name}</CardTitle>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={connection.locality === "cloud" ? "warning" : "success"}>{connection.locality === "cloud" ? "Cloud" : "Local"}</Badge>
        {connection.roles.length > 0 ? (
          connection.roles.map((role) => (
            <Badge key={role} variant="hue">
              {ROLE_NAMES[role]}
            </Badge>
          ))
        ) : (
          <span className="text-meta text-muted-foreground">No role uses this provider.</span>
        )}
      </div>
    </CardHeader>
  );

  // A card with an extra panel stays in one column and grows taller, with the
  // panel under the provider fields. The masonry columns absorb the height.
  return (
    <Card role="region" aria-labelledby={titleId}>
      {header}
      {body}
      {ProviderExtra !== undefined && (
        <div data-slot="provider-extra" className="min-w-0 border-t border-border pt-3">
          <ProviderExtra />
        </div>
      )}
    </Card>
  );
}
