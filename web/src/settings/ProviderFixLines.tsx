import type { Connection } from "../api/settings";

/** Why a provider cannot answer yet, from the cards, or `null` when it can. */
export function notReady(connection: Connection): "not installed" | "no key" | null {
  if (!connection.installed) return "not installed";
  const key = connection.fields.find((field) => field.kind === "secret");
  return key !== undefined && key.required && !key.set ? "no key" : null;
}

/** The install command of a missing provider. The extra comes from the server; an older server only gives the install hint (`uv sync --extra <name>`). */
function installCommand(connection: Connection): string | null {
  const extra = connection.extra ?? /--extra\s+(\S+)/.exec(connection.install_hint ?? "")?.[1];
  return extra === undefined ? connection.install_hint : `uv tool install 'omrs[${extra}]'`;
}

/** One line for each provider that cannot answer yet, with its fix. Nothing when every provider is ready. */
export function ProviderFixLines({ connections }: { connections: Connection[] }) {
  const blocked = connections.flatMap((connection) => {
    const why = notReady(connection);
    return why === null ? [] : [{ connection, why }];
  });
  if (blocked.length === 0) return null;
  return (
    <ul aria-label="Providers that cannot answer yet" className="flex flex-col gap-1 text-meta text-muted-foreground">
      {blocked.map(({ connection, why }) => {
        const command = why === "not installed" ? installCommand(connection) : null;
        return (
          <li key={connection.provider} className="[overflow-wrap:anywhere]">
            {why === "not installed" ? (
              <>
                {`${connection.display_name} is not installed.`}
                {command !== null ? (
                  <>
                    {" Run "}
                    <code dir="ltr" className="font-mono text-code">
                      {command}
                    </code>
                    {" and restart the server."}
                  </>
                ) : null}
              </>
            ) : (
              <>
                {`${connection.display_name} has no key. Add it on the `}
                <a href="#/settings/providers" className="text-primary-label underline underline-offset-4">
                  {`${connection.display_name} card`}
                </a>
                {" under Settings > Providers."}
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}
