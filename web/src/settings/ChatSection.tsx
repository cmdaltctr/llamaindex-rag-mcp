import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useApi } from "../api/ApiProvider";
import { chatSettingsQuery, connectionsQuery } from "../api/queries";
import type { ChatSettings, Connection } from "../api/settings";
import { useSetChatSettings } from "../api/settingsMutations";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { ChatModelForm } from "./ChatModelForm";
import { ChoiceRow, SOURCE } from "./ChoiceRow";
import { isEnvironmentSource } from "./connectionWords";
import { JudgeBlock } from "./JudgeBlock";

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

/** The Chat form with its own save, so a failed save does not outlive the form. */
function ChatForm({ settings, connections, onClose }: { settings: ChatSettings; connections: Connection[]; onClose: () => void }) {
  const save = useSetChatSettings();
  return (
    <ChatModelForm
      initial={{ provider: settings.provider ?? "", model: settings.model ?? "" }}
      connections={connections}
      save={save}
      label="Chat provider and model"
      cloudNote={(host) => `Questions and retrieved passages are sent to ${host}.`}
      canClear={settings.source === "config-file"}
      onClose={onClose}
    />
  );
}

/** Where Chat gets its model. A saved choice is written to `omrs.jsonc` and applies at once to this web server. */
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
        <div className="grid grid-cols-1 items-start gap-3 lg:grid-cols-2">
          <Card role="region" aria-labelledby="settings-chat-model">
            <CardHeader>
              <CardTitle id="settings-chat-model">Answer model</CardTitle>
            </CardHeader>
            {editing ? (
              <ChatForm key={`${settings.provider}|${settings.model}|${settings.source}`} settings={settings} connections={connections} onClose={() => setEditing(false)} />
            ) : (
              <Choice settings={settings} connections={connections} onEdit={() => setEditing(true)} />
            )}
            <ul className="list-disc ps-5 text-meta text-muted-foreground">
              <li>The choice also answers MCP clients of this web server that cannot supply their own model.</li>
              <li>Metadata extraction keeps its own model.</li>
              <li>The claim check judge has its own choice in the next card.</li>
              <li>
                <code className="font-mono text-code">omrs</code> over stdio and the CLI read the same omrs.jsonc at their next launch.
              </li>
            </ul>
          </Card>
          <JudgeBlock connections={connections} />
        </div>
      )}
    </section>
  );
}
