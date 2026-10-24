/**
 * The response of `GET` and `PUT /v1/settings/configuration` (design D10, and
 * D2 of `edit-settings-from-configuration-page`), written by hand until the
 * OpenAPI contract and the generated types carry it.
 */

export type ConfigurationValue = string | number | boolean | null | ConfigurationValue[] | { [key: string]: ConfigurationValue };

export interface ConfigurationSetting {
  /** Dotted path such as `retrieval.top_k`. The text before the first dot names the group. */
  key: string;
  /** The value in force. `null` for a secret, or for a setting with no value. */
  value: ConfigurationValue;
  /** Where the value comes from: `env`, `dotenv`, `config-file`, `keychain`, `key-file` or `default`. */
  source: string;
  applies: "live" | "restart";
  /** True when the file holds a different value from the one the server started with. `value` keeps the launch value; `source` and `saved` describe the next launch. */
  restart_pending: boolean;
  /** The value `omrs.jsonc` holds now, or `null` when the file does not set the key. Always `null` for a key field. */
  saved: ConfigurationValue;
  /** Present only on a set key: its last four characters, or an empty string for a short key. A key field with no key has no `last4`. */
  last4?: string | null;
  /** The page may write this key now. False for a read-only key and for a key from `env` or `dotenv`. */
  editable: boolean;
  /** Why the row has no Edit, or `null` when `editable` is true. */
  read_only_reason: string | null;
  /** The control Edit opens, or `null` for a setting that is not one value (a list or a map). */
  kind: "bool" | "int" | "float" | "text" | "choice" | null;
  /** The accepted values of a `choice` row, else `null`. */
  choices: string[] | null;
  /** The inclusive lower bound of a number, or `null`. */
  min: number | null;
  /** The inclusive upper bound of a number, or `null`. */
  max: number | null;
  /** The setting accepts `null`, so Clear can remove it from `omrs.jsonc`. */
  nullable: boolean;
}

export interface ConfigurationProblem {
  key: string;
  kind: string;
  /** One plain line. It names the rule and never holds the refused value. */
  message: string;
}

export interface ConfigurationState {
  /** The `omrs.jsonc` path. */
  path: string;
  revision: string;
  settings: ConfigurationSetting[];
  problems: ConfigurationProblem[];
  handover: { pending: boolean; folder: string | null };
}

/** One or more keys to write. `null` removes a key from `omrs.jsonc`, so its default applies. */
export type ConfigurationChanges = Record<string, string | number | boolean | null>;
