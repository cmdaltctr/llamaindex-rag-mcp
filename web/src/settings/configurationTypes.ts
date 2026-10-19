/**
 * The response of `GET /v1/settings/configuration` (design D10), written by
 * hand until the OpenAPI contract and the generated types carry it.
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
  /** True when the file holds a different value from the one the server started with. */
  restart_pending: boolean;
  /** Present only on a set key: its last four characters, or an empty string for a short key. A key field with no key has no `last4`. */
  last4?: string | null;
}

export interface ConfigurationProblem {
  key: string;
  kind: string;
  /** One plain line. It names the rule and never holds the refused value. */
  message: string;
}

export interface ConfigurationState {
  /** The `omrg.jsonc` path. */
  path: string;
  revision: string;
  settings: ConfigurationSetting[];
  problems: ConfigurationProblem[];
  handover: { pending: boolean; folder: string | null };
}
