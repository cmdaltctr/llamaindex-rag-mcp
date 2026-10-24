import type { ConfigurationChanges, ConfigurationSetting, ConfigurationValue } from "./configurationTypes";
import { IDENTITY_NOTE } from "./DocumentReadingSection";
import { SettingRow } from "./SettingRow";
import { useSaveConfiguration } from "./useConfiguration";

/** What a restart would apply, for the restart dialog. */
export interface RestartRequest {
  change: string;
  plural: boolean;
  /** One more line in the dialog, such as the index identity note. */
  note?: string;
}

/** Shown when the server sends no reason for a read-only row. */
const READ_ONLY = "Read-only here.";

/** The row text of a value. `null` gives "" so the row shows "Not set". */
function valueText(value: ConfigurationValue): string {
  if (value === null) return "";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/** A key shows at most "Key set" and the last four characters; the server never sends more. */
function shown(setting: ConfigurationSetting): string {
  if (!("last4" in setting)) return valueText(setting.value);
  if (setting.last4 === null || setting.last4 === undefined) return "No key";
  return setting.last4 === "" ? "Key set" : `Key set · ending ${setting.last4}`;
}

/** The typed text as the value the server expects for the row's kind. */
function typedValue(kind: ConfigurationSetting["kind"], text: string): string | number | boolean {
  if (kind === "bool") return text === "true";
  if (kind === "int" || kind === "float") return Number(text.trim());
  return text;
}

export function isChunkingKey(key: string): boolean {
  return key.startsWith("chunking.");
}

interface ConfigurationRowProps {
  setting: ConfigurationSetting;
  /** The revision of the listing this row came from. Every save sends it. */
  revision: string;
  onRestart: (request: RestartRequest) => void;
}

/**
 * One Configuration setting as a mini card. An editable row opens the control
 * for its kind and saves one key; a read-only row shows the server's reason.
 * After a good save of a key that applies at restart, the restart dialog opens.
 */
export function ConfigurationRow({ setting, revision, onRestart }: ConfigurationRowProps) {
  const save = useSaveConfiguration();
  const { key, kind } = setting;

  function send(changes: ConfigurationChanges, done: () => void) {
    save.mutate(
      { revision, changes },
      {
        onSuccess: () => {
          done();
          if (setting.applies !== "restart") return;
          onRestart({ change: key, plural: false, ...(isChunkingKey(key) ? { note: IDENTITY_NOTE } : {}) });
        },
      },
    );
  }

  return (
    <SettingRow
      label={key}
      value={shown(setting)}
      source={setting.source}
      kind={kind ?? "text"}
      choices={setting.choices}
      min={setting.min}
      max={setting.max}
      readOnlyReason={setting.editable && kind !== null ? null : (setting.read_only_reason ?? READ_ONLY)}
      restartPending={setting.restart_pending}
      saved={setting.saved === null ? null : valueText(setting.saved)}
      pending={save.isPending}
      error={save.isError ? save.error : null}
      onSave={(text, done) => send({ [key]: typedValue(kind, text) }, done)}
      {...(setting.nullable ? { onClear: (done: () => void) => send({ [key]: null }, done), clearLabel: "Clear" } : {})}
      onRetry={() => save.reset()}
    />
  );
}
