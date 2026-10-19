import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useApi } from "../api/ApiProvider";
import { chatSettingsQuery, connectionsQuery } from "../api/queries";
import type { ChatSettings, Connection } from "../api/settings";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { ChatModelForm } from "./ChatModelForm";
import { isEnvironmentSource, sourceText } from "./connectionWords";

const SOURCE = "text-meta text-muted-foreground";

function ChoiceRow({ label, value, source }: { label: string; value: string; source: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <p className={SOURCE}>{label}</p>
      <code dir="ltr" className="text-code font-mono [overflow-wrap:anywhere]">
        {value}
      </code>
      <p className={SOURCE}>{sourceText(source)}</p>
    </div>
  );
}

/** The provider and the model as two rows with their source, and Edit unless the environment or `.env` sets them. */
function Choice({ settings, connections, onEdit }: { settings: ChatSettings; connections: Connection[]; onEdit: () => void }) {
  const name = connections.find((connection) => connection.provider === settings.provider)?.display_name ?? settings.provider ?? "Not chosen";
  const locked = settings.locked || isEnvironmentSource(settings.source);
  return (
    <div className="flex flex-col gap-3">
      <ChoiceRow label="Chat provider" value={name} source={settings.source} />
      <ChoiceRow label="Chat model" value={settings.model ?? "Not chosen"} source={settings.source} />
      {locked ? (
        <p className={SOURCE}>{settings.lock_reason ?? "Read-only here."}</p>
      ) : (
        <div>
          <Button type="button" variant="outline" size="sm" aria-label="Edit Chat model" onClick={onEdit}>
            Edit
          </Button>
        </div>
      )}
    </div>
  );
}

/** Where Chat gets its model. A saved choice is written to `omrg.jsonc` and applies at once to this web server. */
export function ChatSection() {
  const api = useApi();
  const chat = useQuery(chatSettingsQuery(api));
  const providers = useQuery(connectionsQuery(api));
  const [editing, setEditing] = useState(false);
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
          {editing ? (
            <ChatModelForm key={`${settings.provider}|${settings.model}|${settings.source}`} settings={settings} connections={connections} onClose={() => setEditing(false)} />
          ) : (
            <Choice settings={settings} connections={connections} onEdit={() => setEditing(true)} />
          )}
          <ul className="list-disc ps-5 text-meta text-muted-foreground">
            <li>The choice also answers MCP clients of this web server that cannot supply their own model.</li>
            <li>Metadata extraction keeps its own model.</li>
            <li>
              <code className="font-mono text-code">omrg</code> over stdio and the CLI read the same omrg.jsonc at their next launch.
            </li>
          </ul>
        </>
      )}
    </section>
  );
}
