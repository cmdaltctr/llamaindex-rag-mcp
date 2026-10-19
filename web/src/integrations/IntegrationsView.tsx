import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { integrationsQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { PageHeader } from "../components/PageHeader";
import { areaById } from "../lib/views";
import { IntegrationCard } from "./IntegrationCard";

/** The optional integrations with live availability and copy-ready install commands. The page never installs anything. */
export function IntegrationsView() {
  const query = useQuery(integrationsQuery(useApi()));
  const integrations = query.data;

  return (
    <section>
      <PageHeader title="Integrations" summary={areaById("integrations").summary} />
      <div role="note" className="mb-4 rounded-panel border border-border bg-muted px-4 py-3 text-meta text-muted-foreground">
        <p>
          Availability reflects the running launch of the server. This page never installs packages. To add an integration, run its command in a
          terminal outside the browser, then restart the server.
        </p>
      </div>
      {integrations === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading integrations.
          </p>
        )
      ) : (
        <ul aria-label="Integrations" className="grid grid-cols-1 items-start gap-3 md:grid-cols-2 xl:grid-cols-3">
          {integrations.map((integration) => (
            <li key={integration.id} className="min-w-0">
              <IntegrationCard integration={integration} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
