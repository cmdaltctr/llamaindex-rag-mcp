import { Lock } from "lucide-react";
import { useId, useState } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../components/ui/tooltip";
import { cellRule, changesOf, restartFor, startText, valueText, type Draft, type RestartRequest } from "./configurationDraft";
import type { ConfigurationSetting, ConfigurationValue } from "./configurationTypes";
import { sourceText } from "./connectionWords";
import { IDENTITY_NOTE } from "./DocumentReadingSection";
import { SaveErrorNotice } from "./SaveErrorNotice";
import { SettingControl } from "./SettingControl";
import { useSaveConfiguration } from "./useConfiguration";
import { rangeRule } from "./validation";

const CODE = "text-code font-mono [overflow-wrap:anywhere]";
const META = "text-meta text-muted-foreground";
/** The Source column shows from the `sm` breakpoint; below it the source words sit under the key. */
const WIDE = "hidden sm:table-cell";
/** Shown when the server sends no reason for a read-only row. */
const READ_ONLY = "Read-only here.";

function isEditable(setting: ConfigurationSetting): boolean {
  return setting.editable && setting.kind !== null;
}

/** A value as the table shows it: On or Off for a boolean, "Not set" for no value or empty text. */
function shownValue(setting: ConfigurationSetting, value: ConfigurationValue): string {
  if (value === null || value === "") return "Not set";
  if (setting.kind === "bool" && typeof value === "boolean") return value ? "On" : "Off";
  return valueText(value);
}

/** A key shows at most "Key set" and the last four characters; the server never sends more. */
function shown(setting: ConfigurationSetting): string {
  if (!("last4" in setting)) return shownValue(setting, setting.value);
  if (setting.last4 === null || setting.last4 === undefined) return "No key";
  return setting.last4 === "" ? "Key set" : `Key set · ending ${setting.last4}`;
}

function SourceWords({ setting }: { setting: ConfigurationSetting }) {
  return (
    <>
      <span className={META}>{sourceText(setting.source)}</span>
      {setting.restart_pending ? <Badge variant="warning">Restart to apply</Badge> : null}
    </>
  );
}

/**
 * The lock on a read-only row. Hover or keyboard focus opens a tooltip that
 * says the setting cannot be changed on this page, and why.
 */
function ReadOnlyLock({ reason }: { reason: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span role="img" aria-label={reason} tabIndex={0} className="inline-flex shrink-0 rounded-small text-muted-foreground">
          <Lock size={16} aria-hidden="true" />
        </span>
      </TooltipTrigger>
      <TooltipContent className="flex flex-col gap-0.5">
        <span className="font-semibold">Read-only on this page.</span>
        <span>{reason}</span>
      </TooltipContent>
    </Tooltip>
  );
}

/** The value in force as text, a lock with the reason on a read-only row, and the next launch value while a restart waits. */
function ValueText({ setting }: { setting: ConfigurationSetting }) {
  const value = shown(setting);
  const reason = isEditable(setting) ? null : (setting.read_only_reason ?? READ_ONLY);
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-1.5">
        {value === "Not set" ? (
          <span className="text-ui">{value}</span>
        ) : (
          <span dir="ltr" className={CODE}>
            {value}
          </span>
        )}
        {reason !== null ? <ReadOnlyLock reason={reason} /> : null}
      </div>
      {setting.restart_pending ? (
        <p className={META}>
          {"Next launch: "}
          <code dir="ltr" className={CODE}>
            {setting.saved === null ? "default" : shownValue(setting, setting.saved)}
          </code>
        </p>
      ) : null}
    </div>
  );
}

interface EditCellProps {
  setting: ConfigurationSetting;
  text: string;
  onChange: (text: string) => void;
}

/**
 * The control of one editable cell and its rule. A number always shows its
 * range as a hint; a rule shows in the error colour once a changed text breaks it.
 */
function EditCell({ setting, text, onChange }: EditCellProps) {
  const id = useId();
  const kind = setting.kind ?? "text";
  const broken = text === startText(setting) ? null : cellRule(setting, text);
  const number = kind === "int" || kind === "float";
  const rule = broken ?? (number ? rangeRule(setting.min, setting.max, kind === "int") : null);
  return (
    <div className="flex flex-col gap-1">
      <SettingControl
        id={id}
        label={setting.key}
        kind={kind}
        typed={text}
        choices={setting.choices ?? []}
        min={setting.min}
        max={setting.max}
        refusal={broken}
        onChange={onChange}
        describedBy={rule !== null ? `${id}-rule` : undefined}
        className="w-full max-w-xs"
      />
      {rule !== null ? (
        <p id={`${id}-rule`} className={broken !== null ? "text-meta text-status-error-label" : META}>
          {rule}
        </p>
      ) : null}
    </div>
  );
}

interface SettingRowsProps {
  setting: ConfigurationSetting;
  /** The typed text of the cell in edit mode, or `null` when the table is locked. */
  text: string | null;
  onChange: (text: string) => void;
}

/** One setting as a table row, plus a reason row for a read-only setting in edit mode. */
function SettingRows({ setting, text, onChange }: SettingRowsProps) {
  const editing = text !== null;
  const control = editing && isEditable(setting);
  const reasonRow = editing && !isEditable(setting);
  return (
    <>
      <TableRow className={reasonRow ? "border-b-0" : undefined}>
        <TableCell className="align-top">
          <code dir="ltr" className={CODE}>
            {setting.key}
          </code>
          <div className="mt-1 flex flex-wrap items-center gap-2 sm:hidden">
            <SourceWords setting={setting} />
          </div>
        </TableCell>
        <TableCell className="align-top">{control ? <EditCell setting={setting} text={text} onChange={onChange} /> : <ValueText setting={setting} />}</TableCell>
        <TableCell className={`${WIDE} align-top`}>
          <div className="flex flex-wrap items-center gap-2">
            <SourceWords setting={setting} />
          </div>
        </TableCell>
      </TableRow>
      {reasonRow ? (
        <TableRow>
          <TableCell colSpan={3} className={`${META} pt-0`}>
            {setting.read_only_reason ?? READ_ONLY}
          </TableCell>
        </TableRow>
      ) : null}
    </>
  );
}

export interface ConfigurationTableProps {
  /** The block title, such as "Retrieval". */
  title: string;
  settings: ConfigurationSetting[];
  /** The revision of the listing these rows came from. Save sends it. */
  revision: string;
  /** True while this table is in edit mode. The parent remounts the table when it changes, which drops the draft. */
  editing: boolean;
  /** Called on Edit. The parent decides whether this table opens. */
  onEdit: () => void;
  /** Called on Cancel and after a good save: the table locks. */
  onClose: () => void;
  /** Called as the draft changes, with true while a cell differs from its start. */
  onDirty: (dirty: boolean) => void;
  onRestart: (request: RestartRequest) => void;
}

/**
 * One Configuration block: a card with the title and Edit, then a Setting |
 * Value | Source table. Edit unlocks every editable cell; Save sends every
 * changed cell in one request, so the server writes all of them or none.
 */
export function ConfigurationTable({ title, settings, revision, editing, onEdit, onClose, onDirty, onRestart }: ConfigurationTableProps) {
  const save = useSaveConfiguration();
  const [draft, setDraft] = useState<Draft>({});
  const textOf = (setting: ConfigurationSetting) => draft[setting.key] ?? startText(setting);
  const changes = changesOf(settings, draft);
  const changed = Object.keys(changes).length > 0;
  const broken = settings.some((setting) => isEditable(setting) && textOf(setting) !== startText(setting) && cellRule(setting, textOf(setting)) !== null);

  function change(key: string, text: string) {
    const next = { ...draft, [key]: text };
    setDraft(next);
    onDirty(Object.keys(changesOf(settings, next)).length > 0);
  }

  function submit() {
    save.mutate(
      { revision, changes },
      {
        onSuccess: () => {
          const request = restartFor(settings, changes);
          onClose();
          if (request !== null) onRestart(request);
        },
      },
    );
  }

  return (
    <TooltipProvider>
      <Card role="group" aria-label={title}>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>{title}</CardTitle>
          {!settings.some(isEditable) ? null : editing ? (
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" size="sm" onClick={onClose}>
                Cancel
              </Button>
              <Button type="button" size="sm" disabled={!changed || broken || save.isPending} onClick={submit}>
                Save
              </Button>
            </div>
          ) : (
            <Button type="button" variant="outline" size="sm" aria-label={`Edit ${title}`} onClick={onEdit}>
              Edit
            </Button>
          )}
        </CardHeader>
        {settings.some((setting) => setting.key.startsWith("chunking.")) ? <p className={META}>{IDENTITY_NOTE}</p> : null}
        {save.isError ? <SaveErrorNotice error={save.error} onRetry={() => save.reset()} /> : null}
        <Table aria-label={title}>
          <TableHeader>
            <TableRow>
              <TableHead scope="col">Setting</TableHead>
              <TableHead scope="col">Value</TableHead>
              <TableHead scope="col" className={WIDE}>
                Source
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {settings.map((setting) => (
              <SettingRows key={setting.key} setting={setting} text={editing ? textOf(setting) : null} onChange={(text) => change(setting.key, text)} />
            ))}
          </TableBody>
        </Table>
      </Card>
    </TooltipProvider>
  );
}
