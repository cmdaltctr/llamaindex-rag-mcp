/**
 * Typed client for the Settings routes: health, provider connections, the
 * server log and MCP access. Shapes follow `openapi.yaml` (`getConnections`,
 * `testConnection`, `listProviderModels`, `saveProviderFields`, `saveProviderKey`,
 * `removeProviderKey`, `getChatSettings`, `setChatSettings`, `testChatModel`, `getJudgeSettings`, `setJudgeSettings`, `getLogs`, `streamLogs`, `getMcpState`, `setMcpEnabled`,
 * `rotateMcpToken`, `revokeMcpToken`, `getWebPort`, `setWebPort`,
 * `getUploadLimit`, `setUploadLimit`).
 * No response here ever holds a provider key; the MCP token appears once, in
 * the response that creates it.
 */
import type { ApiClient, CallOptions } from "./client";

/** Options of a Settings write. `revision` is the stamp of `omrs.jsonc` last read; a file changed on disk since gives 409. */
export interface SaveOptions extends CallOptions {
  revision?: string;
}

export interface Health {
  status: "ok";
  /** False while the server starts or shuts down. */
  ready: boolean;
  /** The installed OMRS package version. */
  version: string;
}

export const CONNECTION_ROLES = ["embeddings", "answers", "metadata", "verification"] as const;
export type ConnectionRole = (typeof CONNECTION_ROLES)[number];

/** Where a value comes from. `env` and `dotenv` lock it. A key also comes from `config-file`, `keychain`, `key-file` or `none`. */
export type FieldSource = "env" | "dotenv" | "config-file" | "keychain" | "key-file" | "default" | "none";

export interface ProviderField {
  id: string;
  label: string;
  kind: "url" | "secret" | "int";
  /** Smallest allowed value of an `int` field; `null` for other kinds. */
  min: number | null;
  /** Largest allowed value of an `int` field; `null` for other kinds. */
  max: number | null;
  /** The address of a `url` field, or the number of an `int` field. A key is never returned. */
  value: string | number | null;
  source: FieldSource;
  locked: boolean;
  /** Plain words for the lock, such as the variable to remove. */
  lock_reason: string | null;
  /** False for a key the provider can run without, such as a local OpenAI-compatible server. */
  required: boolean;
  /** Whether a key is set. */
  set: boolean;
  /** The last four characters of a key, or `null`. */
  last4: string | null;
  /** `keychain-missing` or `keychain-unreadable` when the stored key cannot be used; otherwise `null`. */
  state: string | null;
}

export interface ReadOnlyValue {
  label: string;
  value: string;
}

export interface Connection {
  /** The registry name, such as `ollama`. */
  provider: string;
  display_name: string;
  locality: "local" | "cloud";
  installed: boolean;
  /** The install command when the provider is not installed. */
  install_hint: string | null;
  fields: ProviderField[];
  read_only: ReadOnlyValue[];
  roles: ConnectionRole[];
}

export interface ConnectionList {
  status: "ok";
  /** The server's working directory. The settings read `<config_dir>/.env`. */
  config_dir: string;
  /** The read-only user config folder, with `~` for the home folder. */
  user_config_dir: string;
  keychain: "available" | "unavailable";
  /** Stamp of `omrs.jsonc` at this read. A save sends it back, so a file changed on disk gives 409. */
  revision: string;
  connections: Connection[];
}

export interface ConnectionTestResult {
  status: "ok";
  reachable: boolean;
  /** `null` when reachable; otherwise `refused`, `timeout`, `unauthorised`, `not-configured` or `http-<status>`. */
  reason: string | null;
}

export interface ProviderModels {
  status: "ok";
  reachable: boolean;
  reason: string | null;
  models: string[];
  /** True when the server cut the list at its limit. */
  truncated: boolean;
}

/** Typed field values for a test or a model list. Nothing is saved. */
export type FieldValues = Record<string, string>;

export interface ChatChoice {
  provider: string;
  model: string;
}

export interface ChatSettings {
  status: "ok";
  revision: string;
  provider: string | null;
  model: string | null;
  source: "env" | "dotenv" | "config-file" | "default";
  locked: boolean;
  lock_reason: string | null;
  enabled: boolean;
  ready: boolean;
  /** `disabled`, `unknown-provider`, `not-installed` or `not-configured` when not ready. */
  reason: string | null;
}

/** Why the claim check judge is not ready (`GET /v1/settings/judge`). `no-model`: the judge model in force is empty. */
export type JudgeNotReadyReason = "disabled" | "unknown-provider" | "not-installed" | "not-configured" | "no-model";

/** The claim check judge. A profile decides per collection whether claims are checked, so this holds no on/off state. */
export interface JudgeSettings {
  status: "ok";
  revision: string;
  /** The provider as set: a registry name, or the alias `cloud` or `local`. */
  provider: string;
  /** The registry provider the alias resolves to, such as `openrouter`. */
  resolved_provider: string;
  /** `""` when no judge model is set. */
  model: string;
  source: "env" | "dotenv" | "config-file" | "default";
  locked: boolean;
  lock_reason: string | null;
  enabled: boolean;
  ready: boolean;
  /** Why the judge is not ready, or `null` when it is ready. */
  reason: JudgeNotReadyReason | null;
}

export interface ChatTestResult {
  status: "ok";
  ok: boolean;
  /** `null` when ok; otherwise a fixed reason such as `timeout` or `empty-reply`. */
  reason: string | null;
  elapsed_ms: number;
}

export const LOG_LEVELS = ["debug", "info", "warning", "error", "critical"] as const;
export type LogLevel = (typeof LOG_LEVELS)[number];

export interface LogRecord {
  seq: number;
  /** ISO 8601, UTC. */
  time: string;
  level: LogLevel;
  logger: string;
  /** Redacted by the server. */
  message: string;
}

export interface LogList {
  status: "ok";
  records: LogRecord[];
  last_seq: number;
}

export interface McpState {
  status: "ok";
  revision: string;
  enabled: boolean;
  /** Where the on/off state comes from: `env`, `dotenv`, `config-file` or `default`. */
  source: string;
  /** The full `/mcp` address on the bound host and port. */
  url: string;
  token: { exists: boolean; created_at: string | null };
}

export interface McpTokenCreated {
  status: "ok";
  /** Shown in this response only. */
  token: string;
  created_at: string;
}

export interface McpTokenRevoked {
  status: "ok";
  /** False when no token existed. */
  revoked: boolean;
}

export interface WebPortState {
  status: "ok";
  revision: string;
  /** Used at the next launch when `--port` is not given, or `null`. */
  saved: number | null;
  /** The port this server listens on now. */
  bound: number;
}

/** Where the upload limit in force came from. `launch` locks it for this server run. */
export type UploadLimitSource = "launch" | "config-file" | "default";

export interface UploadLimitState {
  status: "ok";
  revision: string;
  /** The per-file limit in force now. */
  max_bytes: number;
  source: UploadLimitSource;
  /** The value saved in Settings, or `null`. */
  saved_mib: number | null;
  default_mib: number;
  /** The allowed range for a saved value, in whole MiB. */
  min_mib: number;
  max_mib: number;
}

/** The server-sent event stream of log records. Open it with `?after=<last seq>`. */
export const LOG_STREAM_PATH = "/v1/logs/stream";

export function getHealth(api: ApiClient, options: CallOptions = {}): Promise<Health> {
  return api.request<Health>("GET", "/v1/health", { signal: options.signal });
}

export function getConnections(api: ApiClient, options: CallOptions = {}): Promise<ConnectionList> {
  return api.request<ConnectionList>("GET", "/v1/connections", { signal: options.signal });
}

/** Contacts a provider. Typed `fields` are tested and not saved. OpenRouter's test is a cloud request. */
export function testConnection(api: ApiClient, provider: string, fields: FieldValues = {}, options: CallOptions = {}): Promise<ConnectionTestResult> {
  return api.request<ConnectionTestResult>("POST", `/v1/connections/${provider}/test`, { body: { fields }, signal: options.signal });
}

/** Asks the provider for its model names. Typed `fields` are used and not saved. */
export function listProviderModels(api: ApiClient, provider: string, fields: FieldValues = {}, options: CallOptions = {}): Promise<ProviderModels> {
  return api.request<ProviderModels>("POST", `/v1/connections/${provider}/models`, { body: { fields }, signal: options.signal });
}

/** Saves addresses and whole numbers, or clears one with `null`. */
export function saveProviderFields(api: ApiClient, provider: string, fields: Record<string, string | number | null>, options: SaveOptions = {}): Promise<unknown> {
  return api.request<unknown>("PUT", `/v1/connections/${provider}`, { body: { fields, revision: options.revision }, signal: options.signal });
}

/** Saves a key to the system keychain. The response never holds the key. */
export function saveProviderKey(api: ApiClient, provider: string, apiKey: string, options: SaveOptions = {}): Promise<unknown> {
  return api.request<unknown>("PUT", `/v1/connections/${provider}/key`, { body: { api_key: apiKey, revision: options.revision }, signal: options.signal });
}

export function removeProviderKey(api: ApiClient, provider: string, options: SaveOptions = {}): Promise<unknown> {
  return api.request<unknown>("DELETE", `/v1/connections/${provider}/key`, { body: options.revision === undefined ? undefined : { revision: options.revision }, signal: options.signal });
}

export function getChatSettings(api: ApiClient, options: CallOptions = {}): Promise<ChatSettings> {
  return api.request<ChatSettings>("GET", "/v1/settings/chat", { signal: options.signal });
}

/** A clear sends only the revision, so the server can tell it from a choice. With no revision a clear sends `null`. */
function chatBody(choice: ChatChoice | null, revision: string | undefined): unknown {
  if (choice === null && revision === undefined) return null;
  return { ...choice, revision };
}

/** Saves the Chat provider and model, or clears the saved choice with `null`. */
export function setChatSettings(api: ApiClient, choice: ChatChoice | null, options: SaveOptions = {}): Promise<unknown> {
  return api.request<unknown>("PUT", "/v1/settings/chat", { body: chatBody(choice, options.revision), signal: options.signal });
}

/** Sends one short prompt to the typed choice, or to the saved choice when none is given. Nothing is saved. */
export function testChatModel(api: ApiClient, choice: ChatChoice | null = null, options: CallOptions = {}): Promise<ChatTestResult> {
  return api.request<ChatTestResult>("POST", "/v1/settings/chat/test", { body: choice ?? {}, signal: options.signal });
}

export function getJudgeSettings(api: ApiClient, options: CallOptions = {}): Promise<JudgeSettings> {
  return api.request<JudgeSettings>("GET", "/v1/settings/judge", { signal: options.signal });
}

/** Saves the judge provider and model as one unit, or clears both with `null`. A save never writes an alias. */
export function setJudgeSettings(api: ApiClient, choice: ChatChoice | null, options: SaveOptions = {}): Promise<unknown> {
  return api.request<unknown>("PUT", "/v1/settings/judge", { body: chatBody(choice, options.revision), signal: options.signal });
}

export function getLogs(api: ApiClient, after = 0, options: CallOptions = {}): Promise<LogList> {
  return api.request<LogList>("GET", "/v1/logs", { query: { after }, signal: options.signal });
}

export function getMcpState(api: ApiClient, options: CallOptions = {}): Promise<McpState> {
  return api.request<McpState>("GET", "/v1/mcp", { signal: options.signal });
}

export function setMcpEnabled(api: ApiClient, enabled: boolean, options: SaveOptions = {}): Promise<McpState> {
  return api.request<McpState>("PUT", "/v1/mcp", { body: { enabled, revision: options.revision }, signal: options.signal });
}

/** Creates the token, or replaces the existing one. Clients that hold the old token stop working. */
export function rotateMcpToken(api: ApiClient, options: CallOptions = {}): Promise<McpTokenCreated> {
  return api.request<McpTokenCreated>("POST", "/v1/mcp/token", { body: {}, signal: options.signal });
}

export function revokeMcpToken(api: ApiClient, options: CallOptions = {}): Promise<McpTokenRevoked> {
  return api.request<McpTokenRevoked>("DELETE", "/v1/mcp/token", { signal: options.signal });
}

export function getWebPort(api: ApiClient, options: CallOptions = {}): Promise<WebPortState> {
  return api.request<WebPortState>("GET", "/v1/settings/web-port", { signal: options.signal });
}

/** Saves the port for the next launch, or clears it with `null`. The running server does not rebind. */
export function setWebPort(api: ApiClient, port: number | null, options: SaveOptions = {}): Promise<WebPortState> {
  return api.request<WebPortState>("PUT", "/v1/settings/web-port", { body: { port, revision: options.revision }, signal: options.signal });
}

export function getUploadLimit(api: ApiClient, options: CallOptions = {}): Promise<UploadLimitState> {
  return api.request<UploadLimitState>("GET", "/v1/settings/upload-limit", { signal: options.signal });
}

/** Saves the per-file limit in whole MiB, or returns to the default with `null`. It applies to new uploads at once. */
export function setUploadLimit(api: ApiClient, maxMib: number | null, options: SaveOptions = {}): Promise<UploadLimitState> {
  return api.request<UploadLimitState>("PUT", "/v1/settings/upload-limit", { body: { max_mib: maxMib, revision: options.revision }, signal: options.signal });
}
