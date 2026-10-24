/**
 * The draft of one Configuration table in edit mode (design D2 and D3 of
 * `edit-configuration-in-tables`): the text each control starts with, the
 * rule a typed text breaks, and the change set one Save sends.
 */
import type { ConfigurationChanges, ConfigurationSetting, ConfigurationValue } from "./configurationTypes";
import { IDENTITY_NOTE } from "./DocumentReadingSection";
import { numberIn, rangeRule, wholeNumberIn } from "./validation";

/** The typed text of each cell, by key. */
export type Draft = Record<string, string>;

/** What a restart would apply, for the restart dialog. */
export interface RestartRequest {
  change: string;
  plural: boolean;
  /** One more line in the dialog, such as the index identity note. */
  note?: string;
}

const ENTER_A_VALUE = "Enter a value.";

/** A value as text. `null` gives "", a list or a map gives its JSON. */
export function valueText(value: ConfigurationValue): string {
  if (value === null) return "";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/**
 * The text a cell's control starts with.
 *
 * Args:
 *   setting: The row from the listing.
 *
 * Returns:
 *   The saved value when the row waits for a restart, else the value in force,
 *   as text. A boolean gives "true" or "false"; no value gives "".
 */
export function startText(setting: ConfigurationSetting): string {
  return valueText(setting.restart_pending ? setting.saved : setting.value);
}

/**
 * The rule a typed text breaks, checked before any request.
 *
 * Args:
 *   setting: The row the text is for.
 *   text: The typed text.
 *
 * Returns:
 *   The rule as one line, such as "Enter 1 to 8.", or `null` when the text
 *   passes. An empty text passes only on an optional setting.
 */
export function cellRule(setting: ConfigurationSetting, text: string): string | null {
  if (setting.kind === "bool") return null;
  if (text.trim() === "") return setting.nullable ? null : ENTER_A_VALUE;
  const { min, max } = setting;
  if (setting.kind === "int") return wholeNumberIn(min, max, rangeRule(min, max, true))(text);
  if (setting.kind === "float") return numberIn(min, max, rangeRule(min, max, false))(text);
  return null;
}

/** The typed text as the value the server expects for the row's kind. */
function typedValue(setting: ConfigurationSetting, text: string): string | number | boolean | null {
  if (setting.nullable && text.trim() === "") return null;
  if (setting.kind === "bool") return text === "true";
  if (setting.kind === "int" || setting.kind === "float") return Number(text.trim());
  return text;
}

/**
 * The change set for one Save.
 *
 * Args:
 *   settings: The rows of the table.
 *   draft: The typed text of each cell, by key.
 *
 * Returns:
 *   One entry for each cell whose text differs from its start text, typed for
 *   its kind. An emptied optional setting gives `null`, which removes the key.
 */
export function changesOf(settings: ConfigurationSetting[], draft: Draft): ConfigurationChanges {
  const changes: ConfigurationChanges = {};
  for (const setting of settings) {
    const text = draft[setting.key];
    if (text === undefined || text === startText(setting)) continue;
    changes[setting.key] = typedValue(setting, text);
  }
  return changes;
}

/**
 * The restart dialog request after a good save, or `null` when no saved key
 * applies at restart. One key is named; more are counted.
 *
 * Args:
 *   settings: The rows of the table.
 *   changes: The change set that was saved.
 */
export function restartFor(settings: ConfigurationSetting[], changes: ConfigurationChanges): RestartRequest | null {
  const keys = settings.filter((setting) => setting.applies === "restart" && setting.key in changes).map((setting) => setting.key);
  if (keys.length === 0) return null;
  const request: RestartRequest = keys.length === 1 ? { change: keys[0]!, plural: false } : { change: `${keys.length} changed settings`, plural: true };
  return Object.keys(changes).some((key) => key.startsWith("chunking.")) ? { ...request, note: IDENTITY_NOTE } : request;
}
