import { useState } from "react";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardInset, CardTitle } from "../components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { useReturnFocus } from "../studio/useReturnFocus";
import type { RestartRequest } from "./configurationDraft";
import { ConfigurationTable } from "./ConfigurationTable";
import { CopyButton } from "./CopyButton";
import type { ConfigurationSetting, ConfigurationState } from "./configurationTypes";
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

interface DiscardDialogProps {
  /** The title of the block with changes, or `null` to keep the dialog closed. */
  block: string | null;
  onKeep: () => void;
  onDiscard: () => void;
}

/** Asks before Edit on another block drops the changes in the open one. */
function DiscardDialog({ block, onKeep, onDiscard }: DiscardDialogProps) {
  const returnFocus = useReturnFocus();
  return (
    <Dialog open={block !== null} onOpenChange={(next) => (next ? undefined : onKeep())}>
      <DialogContent {...returnFocus}>
        <DialogHeader>
          <DialogTitle>{`Discard your changes to ${block ?? ""}?`}</DialogTitle>
          <DialogDescription>Only one table can be edited at a time. Nothing in this table has been saved.</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onKeep}>
            Keep editing
          </Button>
          <Button type="button" variant="destructive" onClick={onDiscard}>
            Discard
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface ConfigurationViewProps {
  state: ConfigurationState;
  /** Called when the person asks to restart for the settings that wait. */
  onRestart: (request: RestartRequest) => void;
}

/**
 * The settings grouped by block, one table in a card each, with the file path,
 * the problems found in the file and a restart prompt. Only one table is in
 * edit mode at a time; Edit on another block asks first when the open one has changes.
 */
export function ConfigurationView({ state, onRestart }: ConfigurationViewProps) {
  const waiting = state.settings.filter((setting) => setting.restart_pending);
  const [open, setOpen] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [asking, setAsking] = useState<string | null>(null);

  function openBlock(name: string | null) {
    setOpen(name);
    setDirty(false);
    setAsking(null);
  }

  function requestEdit(name: string) {
    if (open !== null && open !== name && dirty) return setAsking(name);
    openBlock(name);
  }

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
        <ConfigurationTable
          // A new key on open and on close remounts the table, so a closed table holds no draft.
          key={open === group.name ? `${group.name}:edit` : group.name}
          title={title(group.name)}
          settings={group.settings}
          revision={state.revision}
          editing={open === group.name}
          onEdit={() => requestEdit(group.name)}
          onClose={() => openBlock(null)}
          onDirty={setDirty}
          onRestart={onRestart}
        />
      ))}
      <DiscardDialog block={open !== null && asking !== null ? title(open) : null} onKeep={() => setAsking(null)} onDiscard={() => openBlock(asking)} />
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
