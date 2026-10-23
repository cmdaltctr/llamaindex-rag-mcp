import type { Connection } from "../api/settings";
import { formatRoute } from "../lib/routes";

/** The extra that supplies a provider. An older server sends only the install hint (`uv sync --extra <name>`). */
function providerExtra(connection: Connection): string | null {
  return connection.extra ?? /--extra\s+(\S+)/.exec(connection.install_hint ?? "")?.[1] ?? null;
}

/**
 * A link to the Integrations entry of a provider that is not installed, such
 * as `#/integrations/anthropic`. The entry's id is its extra. Without an
 * extra, the link opens the Integrations page.
 */
export function IntegrationLink({ connection }: { connection: Connection }) {
  return (
    <a href={formatRoute({ area: "integrations", entry: providerExtra(connection) })} className="text-primary-label underline underline-offset-4">
      {`Install ${connection.display_name} from Integrations`}
    </a>
  );
}
