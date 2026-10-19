import { useState } from "react";
import { ErrorNotice } from "../components/ErrorNotice";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { sourceText } from "./connectionWords";
import { CopyButton } from "./CopyButton";
import type { ConfigurationSetting, ConfigurationState, ConfigurationValue } from "./configurationTypes";
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

function valueText(value: ConfigurationValue): string {
  if (value === null) return "Not set";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/** A key shows at most "Key set" and its last four characters; the server never sends more. */
function shown(setting: ConfigurationSetting): string {
  if (setting.last4 === undefined) return valueText(setting.value);
  if (setting.last4 === null) return "No key";
  return setting.last4 === "" ? "Key set" : `Key set · ending ${setting.last4}`;
}

export interface RestartRequest {
  change: string;
  plural: boolean;
}

interface ConfigurationViewProps {
  state: ConfigurationState;
  /** Called when the person asks to restart for the settings that wait. */
  onRestart: (request: RestartRequest) => void;
}

/** The settings, read-only, grouped by block, with the file path, the problems found in the file and a restart prompt. */
export function ConfigurationView({ state, onRestart }: ConfigurationViewProps) {
  const waiting = state.settings.filter((setting) => setting.restart_pending);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <p className="text-meta text-muted-foreground">Settings file</p>
        <code dir="ltr" className={CODE}>
          {state.path}
        </code>
        <div>
          <CopyButton text={state.path} what="settings file path" />
        </div>
      </div>
      {state.handover.pending ? (
        <div className="flex flex-col gap-1">
          <p className="text-ui">Saved settings could not be moved to omrg.jsonc</p>
          {state.handover.folder !== null ? (
            <code dir="ltr" className={CODE}>
              {state.handover.folder}
            </code>
          ) : null}
        </div>
      ) : null}
      {state.problems.length > 0 ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-subsection-title font-semibold">Problems in omrg.jsonc</h3>
          <ul aria-label="Problems in omrg.jsonc" className="flex flex-col gap-1">
            {state.problems.map((problem) => (
              <li key={`${problem.key}-${problem.kind}`} className="text-ui">
                <code dir="ltr" className={CODE}>
                  {problem.key}
                </code>
                {` ${problem.message}`}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {waiting.length > 0 ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-ui">{waiting.length === 1 ? "One setting waits for a restart." : `${waiting.length} settings wait for a restart.`}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onRestart(waiting.length === 1 ? { change: waiting[0]!.key, plural: false } : { change: `${waiting.length} changed settings`, plural: true })}
          >
            Restart…
          </Button>
        </div>
      ) : null}
      {groupSettings(state.settings).map((group) => (
        <div key={group.name} className="flex flex-col gap-2">
          <h3 className="text-subsection-title font-semibold">{title(group.name)}</h3>
          <Table aria-label={title(group.name)}>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Setting</TableHead>
                <TableHead scope="col">Value</TableHead>
                <TableHead scope="col">Source</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {group.settings.map((setting) => (
                <TableRow key={setting.key}>
                  <TableCell>
                    <code dir="ltr" className={CODE}>
                      {setting.key}
                    </code>
                  </TableCell>
                  <TableCell>
                    <span dir="ltr" className={CODE}>
                      {shown(setting)}
                    </span>
                  </TableCell>
                  <TableCell>
                    <span className="text-meta text-muted-foreground">{sourceText(setting.source)}</span>
                    {setting.restart_pending ? (
                      <Badge variant="warning" className="ms-2">
                        Restart to apply
                      </Badge>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
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
      <RestartDialog change={restart?.change ?? null} plural={restart?.plural ?? false} onLater={() => setRestart(null)} />
    </section>
  );
}
