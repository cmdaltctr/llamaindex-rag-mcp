import type { Connection, ConnectionRole } from "../api/settings";

export const ROLE_NAMES: Record<ConnectionRole, string> = {
  embeddings: "Embeddings",
  answers: "Answers",
  metadata: "Metadata",
  verification: "Verification",
};

const HTTP_REASON = /^http-(\d{3})$/;
const KNOWN_REASONS = ["refused", "timeout", "unauthorised", "not-configured", "not-installed", "empty-reply", "failed"];

/** The fixed reasons the server may return. Anything else is not shown as raw text. */
export function isKnownReason(reason: string): boolean {
  return KNOWN_REASONS.includes(reason) || HTTP_REASON.test(reason);
}

/** A plain-words sentence for one connection or Chat test reason. */
export function reasonSentence(reason: string): string {
  switch (reason) {
    case "refused":
      return "The connection was refused. Nothing is listening at that address.";
    case "timeout":
      return "The provider did not answer in time.";
    case "unauthorised":
      return "The key was not accepted by the provider.";
    case "not-configured":
      return "No address or key is configured, so nothing was sent.";
    case "not-installed":
      return "The package for this provider is not installed.";
    case "empty-reply":
      return "The model answered with no text.";
  }
  const status = HTTP_REASON.exec(reason)?.[1];
  return status === undefined ? "The test failed." : `The provider answered with HTTP status ${status}.`;
}

/** One plain line for each reason Chat is not ready. */
export function chatReasonSentence(reason: string | null): string {
  switch (reason) {
    case "disabled":
      return "Answering is turned off on the server.";
    case "unknown-provider":
      return "The chosen provider is not known to this server.";
    case "not-installed":
      return "The package for the chosen provider is not installed.";
    case "not-configured":
      return "Chat has no model connected.";
    default:
      return "Chat is not ready.";
  }
}

/** True when the address names this machine, so text sent to it stays here. */
export function isLoopback(address: string): boolean {
  try {
    const host = new URL(address).hostname.replace(/^\[|\]$/g, "");
    return host === "localhost" || host === "::1" || /^127(\.\d{1,3}){3}$/.test(host);
  } catch {
    return false;
  }
}

/** The text sent to a cloud provider goes to this host. A provider not listed here is named by its display name. */
const CLOUD_HOSTS: Record<string, string> = { openrouter: "openrouter.ai" };

export function cloudHost(connection: Connection): string {
  return CLOUD_HOSTS[connection.provider] ?? connection.display_name;
}

/**
 * The plain words for where a setting value comes from. One map for every
 * Settings row. `env` and `dotenv` are locked: the page cannot change them.
 */
export const SOURCE_WORDS: Record<string, string> = {
  env: "Set in the environment. Change it there.",
  dotenv: "Set in .env. Change it there.",
  "config-file": "from omrs.jsonc",
  keychain: "in system keychain",
  "key-file": "from key file",
  default: "default",
  none: "not set",
  init: "set when the server started",
};

/** The words for a source, followed by `detail` (a variable name or a path) when given. An unknown source shows as it is. */
export function sourceText(source: string, detail?: string | null): string {
  const words = SOURCE_WORDS[source] ?? source;
  return detail ? `${words} ${detail}` : words;
}

/** True when the environment or `.env` sets the value, so the page cannot change it. */
export function isEnvironmentSource(source: string): boolean {
  return source === "env" || source === "dotenv";
}
