import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useApi } from "../api/ApiProvider";
import type { IntegrationList } from "../api/integrations";
import { integrationsQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { MasonryColumns } from "../components/MasonryColumns";
import { PageHeader } from "../components/PageHeader";
import { areaById } from "../lib/views";
import { IntegrationCard, integrationCardId } from "./IntegrationCard";
import { useIntegrationInstall } from "./useIntegrationInstall";

/** True when the server can install an entry from this page. */
function canInstall(list: IntegrationList): boolean {
  if (list.integrations.some((integration) => integration.installable)) return true;
  return list.install_type === "uv-tool" && !list.integrations.some((integration) => integration.install_reason === "uv-not-found");
}

/**
 * Moves focus to the entry a link names, such as `#/integrations/anthropic`.
 * The focus waits one task, because the shell focuses the page heading after
 * a move between areas, and that runs after this view's effects.
 */
function useFocusEntry(entry: string | null, loaded: boolean) {
  useEffect(() => {
    if (entry === null || !loaded) return;
    const timer = window.setTimeout(() => {
      const card = document.getElementById(integrationCardId(entry));
      card?.scrollIntoView({ block: "nearest" });
      card?.focus();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [entry, loaded]);
}

/** The optional integrations with live availability, an Install action where the server can install, and copy-ready commands. */
export function IntegrationsView({ entry = null }: { entry?: string | null }) {
  const query = useQuery(integrationsQuery(useApi()));
  const list = query.data;
  const control = useIntegrationInstall(list?.install_type);
  useFocusEntry(entry, list !== undefined);

  return (
    <section>
      <PageHeader title="Integrations" summary={areaById("integrations").summary} />
      <div role="note" className="mb-4 rounded-panel border border-border bg-muted px-4 py-3 text-meta text-muted-foreground">
        <p>
          {"Availability reflects the running launch of the server."}
          {list === undefined
            ? null
            : canInstall(list)
              ? " Install adds the packages to the server. A restart makes them available."
              : " This server cannot install from the app. To add an integration, run its command in a terminal outside the app, then restart the server."}
        </p>
      </div>
      {list === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading integrations.
          </p>
        )
      ) : (
        // Masonry, not a grid: a card with an install message is tall, and a
        // grid row would leave a gap beside the short cards next to it.
        <div role="list" aria-label="Integrations">
          <MasonryColumns>
            {list.integrations.map((integration) => (
              <div key={integration.id} role="listitem" className="min-w-0">
                <IntegrationCard integration={integration} installType={list.install_type} control={control} />
              </div>
            ))}
          </MasonryColumns>
        </div>
      )}
    </section>
  );
}
