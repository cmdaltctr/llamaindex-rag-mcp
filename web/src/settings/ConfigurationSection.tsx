import { useState } from "react";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardInset, CardTitle } from "../components/ui/card";
import { ConfigurationRow, isChunkingKey, type RestartRequest } from "./ConfigurationRow";
import { CopyButton } from "./CopyButton";
import type { ConfigurationSetting, ConfigurationState } from "./configurationTypes";
import { IDENTITY_NOTE } from "./DocumentReadingSection";
import { RestartDialog } from "./RestartDialog";
import { useConfiguration } from "./useConfiguration";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";
/** The group of a key with no dot, such as `web_port`. */
const GENERAL = "General";

export interface SettingGroup {
  name: string;
  settings: ConfigurationSetting[];
}

/** Groups settings by the text before the first dot. Groups and settings keep the order of the server. */
export function groupSettings(settings: ConfigurationSetting[]): SettingGroup[] {
  const groups = new Map<string, ConfigurationSetting[]>();
  for (const setting of settings) {
    const dot = setting.key.indexOf(".");
    const name = dot === -1 ? GENERAL : setting.key.slice(0, dot);
    groups.set(name, [...(groups.get(name) ?? []), setting]);
  }
  return [...groups].map(([name, members]) => ({ name, settings: members }));
}

function title(name: string): string {
  return name === GENERAL ? name : name.charAt(0).toUpperCase() + name.slice(1).replace(/_/g, " ");
}

interface ConfigurationViewProps {
  state: ConfigurationState;
  /** Called when the person asks to restart for the settings that wait. */
  onRestart: (request: RestartRequest) => void;
}

/** The settings grouped by block, one mini card each, with the file path, the problems found in the file and a restart prompt. */
export function ConfigurationView({ state, onRestart }: ConfigurationViewProps) {
  const waiting = state.settings.filter((setting) => setting.restart_pending);

  return (
    <div className="flex flex-col gap-4">
      <Card role="region" aria-labelledby="configuration-file">
        <CardHeader>
          <CardTitle id="configuration-file">Settings file</CardTitle>
        </CardHeader>
        <CardInset>
          <code dir="ltr" className={CODE}>
            {state.path}
          </code>
          <div>
            <CopyButton text={state.path} what="settings file path" />
          </div>
        </CardInset>
        {state.handover.pending ? (
          <CardInset>
            <p className="text-ui">Saved settings could not be moved to omrs.jsonc</p>
            {state.handover.folder !== null ? (
              <code dir="ltr" className={CODE}>
                {state.handover.folder}
              </code>
            ) : null}
          </CardInset>
        ) : null}
        {waiting.length > 0 ? (
          <CardInset className="flex-row flex-wrap items-center gap-3">
            <p className="text-ui">{waiting.length === 1 ? "One setting waits for a restart." : `${waiting.length} settings wait for a restart.`}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onRestart(waiting.length === 1 ? { change: waiting[0]!.key, plural: false } : { change: `${waiting.length} changed settings`, plural: true })}
            >
              Restart…
            </Button>
          </CardInset>
        ) : null}
      </Card>
      {state.problems.length > 0 ? (
        <Card>
          <CardTitle>Problems in omrs.jsonc</CardTitle>
          <ul aria-label="Problems in omrs.jsonc" className="flex flex-col gap-1">
            {state.problems.map((problem) => (
              <li key={`${problem.key}-${problem.kind}`} className="text-ui">
                <code dir="ltr" className={CODE}>
                  {problem.key}
                </code>
                {` ${problem.message}`}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
      {groupSettings(state.settings).map((group) => (
        <Card key={group.name} role="group" aria-label={title(group.name)}>
          <CardTitle>{title(group.name)}</CardTitle>
          {group.settings.some((setting) => isChunkingKey(setting.key)) ? <p className="text-meta text-muted-foreground">{IDENTITY_NOTE}</p> : null}
          {group.settings.map((setting) => (
            <ConfigurationRow key={setting.key} setting={setting} revision={state.revision} onRestart={onRestart} />
          ))}
        </Card>
      ))}
    </div>
  );
}

/** Settings › Configuration: loads `GET /v1/settings/configuration` and hosts the restart dialog. */
export function ConfigurationSection() {
  const query = useConfiguration();
  const [restart, setRestart] = useState<RestartRequest | null>(null);

  return (
    <section aria-labelledby="settings-configuration" className="flex flex-col gap-4">
      <h2 id="settings-configuration" className="text-section-title font-semibold">
        Configuration
      </h2>
      {query.data !== undefined ? (
        <ConfigurationView state={query.data} onRestart={setRestart} />
      ) : query.isError ? (
        <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <p role="status" className="text-meta text-muted-foreground">
          Loading.
        </p>
      )}
      <RestartDialog change={restart?.change ?? null} plural={restart?.plural ?? false} note={restart?.note} onLater={() => setRestart(null)} />
    </section>
  );
}
