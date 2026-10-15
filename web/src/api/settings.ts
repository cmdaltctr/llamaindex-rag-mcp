/**
 * Typed client for the Settings routes: health, provider connections, the
 * server log and MCP access. Shapes follow `openapi.yaml` (`getConnections`,
 * `testConnection`, `getLogs`, `streamLogs`, `getMcpState`, `setMcpEnabled`,
 * `rotateMcpToken`, `revokeMcpToken`, `getWebPort`, `setWebPort`,
 * `getUploadLimit`, `setUploadLimit`).
 * No response here ever holds a provider key; the MCP token appears once, in
 * the response that creates it.
 */
import type { ApiClient, CallOptions } from "./client";

export interface Health {
  status: "ok";
  /** False while the server starts or shuts down. */
  ready: boolean;
  /** The installed OMRG package version. */
  version: string;
}

export const CONNECTION_PROVIDERS = ["ollama", "llamacpp", "openrouter"] as const;
export type ConnectionProvider = (typeof CONNECTION_PROVIDERS)[number];

export const CONNECTION_ROLES = ["embeddings", "answers", "metadata", "verification"] as const;
export type ConnectionRole = (typeof CONNECTION_ROLES)[number];

export interface Connection {
  provider: ConnectionProvider;
  urls: { label: string; url: string }[];
  models: { label: string; name: string }[];
  /** Whether a key is configured. The key itself is never returned. */
  key_set: boolean;
  roles: ConnectionRole[];
}

export interface ConnectionList {
  status: "ok";
  /** The server's working directory. The settings read `<config_dir>/.env`. */
  config_dir: string;
  connections: Connection[];
}

export interface ConnectionTestResult {
  status: "ok";
  reachable: boolean;
  /** `null` when reachable; otherwise `refused`, `timeout`, `unauthorised`, `not-configured` or `http-<status>`. */
  reason: string | null;
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
  enabled: boolean;
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
  /** Used at the next launch when `--port` is not given, or `null`. */
  saved: number | null;
  /** The port this server listens on now. */
  bound: number;
}

/** Where the upload limit in force came from. `launch` locks it for this server run. */
export type UploadLimitSource = "launch" | "saved" | "default";

export interface UploadLimitState {
  status: "ok";
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

/** The only call that contacts a provider. OpenRouter's test is a cloud request. */
export function testConnection(api: ApiClient, provider: ConnectionProvider, options: CallOptions = {}): Promise<ConnectionTestResult> {
  return api.request<ConnectionTestResult>("POST", `/v1/connections/${provider}/test`, { body: {}, signal: options.signal });
}

export function getLogs(api: ApiClient, after = 0, options: CallOptions = {}): Promise<LogList> {
  return api.request<LogList>("GET", "/v1/logs", { query: { after }, signal: options.signal });
}

export function getMcpState(api: ApiClient, options: CallOptions = {}): Promise<McpState> {
  return api.request<McpState>("GET", "/v1/mcp", { signal: options.signal });
}

export function setMcpEnabled(api: ApiClient, enabled: boolean, options: CallOptions = {}): Promise<McpState> {
  return api.request<McpState>("PUT", "/v1/mcp", { body: { enabled }, signal: options.signal });
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
export function setWebPort(api: ApiClient, port: number | null, options: CallOptions = {}): Promise<WebPortState> {
  return api.request<WebPortState>("PUT", "/v1/settings/web-port", { body: { port }, signal: options.signal });
}

export function getUploadLimit(api: ApiClient, options: CallOptions = {}): Promise<UploadLimitState> {
  return api.request<UploadLimitState>("GET", "/v1/settings/upload-limit", { signal: options.signal });
}

/** Saves the per-file limit in whole MiB, or returns to the default with `null`. It applies to new uploads at once. */
export function setUploadLimit(api: ApiClient, maxMib: number | null, options: CallOptions = {}): Promise<UploadLimitState> {
  return api.request<UploadLimitState>("PUT", "/v1/settings/upload-limit", { body: { max_mib: maxMib }, signal: options.signal });
}
