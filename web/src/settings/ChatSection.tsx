import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { chatSettingsQuery, connectionsQuery } from "../api/queries";
import type { ChatSettings, Connection } from "../api/settings";
import { ErrorNotice } from "../components/ErrorNotice";
import { ChatModelForm } from "./ChatModelForm";

function LockedChoice({ settings, connections }: { settings: ChatSettings; connections: Connection[] }) {
  const name = connections.find((connection) => connection.provider === settings.provider)?.display_name ?? settings.provider ?? "No provider";
  return (
    <div className="flex flex-col gap-1">
      <p className="text-ui">
        {name}
        {settings.model !== null ? <> · <code dir="ltr" className="font-mono text-code [overflow-wrap:anywhere]">{settings.model}</code></> : null}
      </p>
      <p className="text-meta text-muted-foreground">
        Set from environment (read-only here){settings.lock_reason !== null ? `. ${settings.lock_reason}` : ""}
      </p>
    </div>
  );
}

/** Where Chat gets its model. The saved choice applies at once to this web server. */
export function ChatSection() {
  const api = useApi();
  const chat = useQuery(chatSettingsQuery(api));
  const providers = useQuery(connectionsQuery(api));
  const settings = chat.data;
  const connections = providers.data?.connections;

  return (
    <section aria-labelledby="settings-chat" className="flex flex-col gap-3">
      <h2 id="settings-chat" className="text-section-title font-semibold">
        Chat
      </h2>
      {settings === undefined || connections === undefined ? (
        chat.isError || providers.isError ? (
          <ErrorNotice error={chat.error ?? providers.error} onRetry={() => void Promise.all([chat.refetch(), providers.refetch()])} />
        ) : (
          <p role="status" className="text-meta text-muted-foreground">
            Loading Chat settings.
          </p>
        )
      ) : (
        <>
          {settings.locked ? (
            <LockedChoice settings={settings} connections={connections} />
          ) : (
            <ChatModelForm
              key={`${settings.provider}|${settings.model}|${settings.source}`}
              settings={settings}
              connections={connections}
            />
          )}
          <ul className="list-disc ps-5 text-meta text-muted-foreground">
            <li>The choice also answers MCP clients of this web server that cannot supply their own model.</li>
            <li>Metadata extraction keeps its own model.</li>
            <li>
              <code className="font-mono text-code">omrg</code> over stdio and the CLI read .env only.
            </li>
          </ul>
        </>
      )}
    </section>
  );
}
