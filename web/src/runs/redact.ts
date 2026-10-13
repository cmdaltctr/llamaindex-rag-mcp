/**
 * Second line of defence for secrets. The server already redacts run
 * settings, failures and events (`core/workspace/redaction.py`); the UI shows
 * those values as given and never tries to recover them. These checks mirror
 * the server rules so a value the server missed is still masked on screen.
 */
export const REDACTED = "[redacted]";

const SECRET_KEY =
  /(?:^|_)(?:api_?key|apikey|key|secret|secrets|password|passwd|pwd|token|access_token|refresh_token|id_token|auth|authorization|bearer|credential|credentials|cookie|session|private_key|signature)$/;
const CREDENTIAL_NAMES = "api_?key|apikey|token|access_token|password|secret|signature|key";
const TEXT_RULES: [RegExp, string][] = [
  [/\b([a-z][a-z0-9+.-]*:\/\/)[^/\s@:]*(?::[^/\s@]*)?@/gi, `$1${REDACTED}@`],
  [new RegExp(`([?&](?:${CREDENTIAL_NAMES})=)[^&#\\s]+`, "gi"), `$1${REDACTED}`],
  [/\b(bearer)\s+(?!\[redacted\])[A-Za-z0-9._~+/=-]{8,}/gi, `$1 ${REDACTED}`],
];

export function isSecretKey(key: string): boolean {
  return SECRET_KEY.test(key.toLowerCase().replace(/-/g, "_"));
}

export function maskText(text: string): string {
  return TEXT_RULES.reduce((current, [pattern, replacement]) => current.replace(pattern, replacement), text);
}

/** The value to display for `key`: a credential key always shows the marker. */
export function safeEntry(key: string, value: unknown): unknown {
  if (isSecretKey(key) && value !== null && value !== undefined && value !== "") return REDACTED;
  return typeof value === "string" ? maskText(value) : value;
}
