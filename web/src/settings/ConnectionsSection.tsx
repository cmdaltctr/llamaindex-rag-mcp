import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { connectionsQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { ConnectionCard } from "./ConnectionCard";

/** Read-only provider settings. Values come from the server's `.env` and change only with a restart. */
export function ConnectionsSection() {
  const query = useQuery(connectionsQuery(useApi()));
  const list = query.data;

  return (
    <section aria-labelledby="settings-connections" className="flex flex-col gap-3">
      <h2 id="settings-connections" className="text-section-title font-semibold">
        Connections
      </h2>
      {list === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading connections.
          </p>
        )
      ) : (
        <>
          <p className="text-meta text-muted-foreground">
            These values come from{" "}
            <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
              {`${list.config_dir}/.env`}
            </code>
            . A change needs a server restart. This page cannot edit them and never shows a key.
          </p>
          <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-2 xl:grid-cols-3">
            {list.connections.map((connection) => (
              <ConnectionCard key={connection.provider} connection={connection} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}
