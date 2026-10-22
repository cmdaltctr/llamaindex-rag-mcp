import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { connectionsQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { ProviderCard } from "./ProviderCard";

/** The provider cards. Addresses and keys are saved to `omrs.jsonc` (keys to the keychain) and apply at once to this web server. */
export function ProvidersSection() {
  const query = useQuery(connectionsQuery(useApi()));
  const list = query.data;

  return (
    <section aria-labelledby="settings-providers" className="flex flex-col gap-3">
      <h2 id="settings-providers" className="text-section-title font-semibold">
        Providers
      </h2>
      {list === undefined ? (
        query.isError ? (
          <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading providers.
          </p>
        )
      ) : (
        <>
          <p className="text-meta text-muted-foreground">
            Saves are written to{" "}
            <code dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
              {`${list.user_config_dir}/omrs.jsonc`}
            </code>{" "}
            and apply at once to this web server. <code className="font-mono text-code">omrs</code> over stdio and the CLI read the same file at their next launch. A value set in the
            environment or in{" "}
            <code dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">
              {`${list.config_dir}/.env`}
            </code>{" "}
            wins and cannot be changed here. A key is never shown again after you save it.
          </p>
          <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-2 xl:grid-cols-3">
            {list.connections.map((connection) => (
              <ProviderCard key={connection.provider} connection={connection} keychain={list.keychain} configDir={list.config_dir} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}
