import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useApi } from "../api/ApiProvider";
import { healthQuery, operationsQuery, sessionQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";

/** One fact: the value, a loading line, or a friendly failure with Retry. */
function Fact<T>({ query, show, quiet = false }: { query: UseQueryResult<T>; show: (data: T) => ReactNode; quiet?: boolean }) {
  if (query.data !== undefined) return <>{show(query.data)}</>;
  // A second fact from the same failed read says so in a word, so one failure raises one alert.
  if (query.isError && quiet) return <span className="text-muted-foreground">Not available</span>;
  if (query.isError) return <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />;
  return <span className="text-muted-foreground">Loading</span>;
}

/** What the running server reports: readiness, session scopes and which pipeline operations work here. */
export function RuntimeSection() {
  const api = useApi();
  const health = useQuery(healthQuery(api));
  const session = useQuery(sessionQuery(api));
  const operations = useQuery(operationsQuery(api));
  const unavailable = operations.data?.filter((operation) => !operation.available) ?? [];

  return (
    <section aria-labelledby="settings-runtime" className="flex flex-col gap-3">
      <h2 id="settings-runtime" className="text-section-title font-semibold">
        Runtime
      </h2>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-x-4 gap-y-2 text-ui">
        <dt className="text-muted-foreground">Server</dt>
        <dd>
          <Fact query={health} show={(data) => (data.ready ? "Ready" : "Starting or shutting down")} />
        </dd>
        <dt className="text-muted-foreground">Session</dt>
        <dd>
          <Fact query={session} show={(data) => data.kind} />
        </dd>
        <dt className="text-muted-foreground">Scopes</dt>
        <dd>
          <Fact query={session} quiet show={(data) => data.scopes.join(", ")} />
        </dd>
        <dt className="text-muted-foreground">Pipeline operations</dt>
        <dd>
          <Fact query={operations} show={(data) => `${data.length - unavailable.length} of ${data.length} available`} />
        </dd>
      </dl>
      {unavailable.length > 0 ? (
        <ul aria-label="Unavailable operations" className="flex flex-col gap-1 text-ui">
          {unavailable.map((operation) => (
            <li key={operation.operation_id}>
              {operation.title}{" "}
              <code dir="ltr" className="text-code font-mono">
                ({operation.operation_id})
              </code>
              : not available in this runtime
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
