import type { LlamacppServerStatus, ServerField } from "../../api/llamacppServer";
import type { ChatSettings, Connection, ConnectionList, LogRecord, McpState, ProviderField, WebPortState } from "../../api/settings";
import { documentsServer, type Handler } from "../../test/fakeDocumentsServer";

/** Fixtures built from the `openapi.yaml` schemas for the Settings routes. */
export const CONFIG_DIR = "/srv/omrg project";

const NO_KEY = { min: null, max: null, value: null, required: true, set: false, last4: null, saved_at: null, state: null, locked: false, lock_reason: null } as const;

export function urlField(id: string, label: string, value: string, source: ProviderField["source"] = "default", lock?: string): ProviderField {
  return { id, label, kind: "url", min: null, max: null, value, source, locked: lock !== undefined, lock_reason: lock ?? null, required: true, set: false, last4: null, saved_at: null, state: null };
}

export function intField(id: string, label: string, value: number, source: ProviderField["source"] = "default", lock?: string): ProviderField {
  return { id, label, kind: "int", min: 2048, max: 262144, value, source, locked: lock !== undefined, lock_reason: lock ?? null, required: true, set: true, last4: null, saved_at: null, state: null };
}

function serverField(id: string, label: string, kind: ServerField["kind"], value: string | number, source: ServerField["source"] = "default", lock?: string): ServerField {
  const range = kind === "int" ? { min: 2048, max: 262144 } : { min: null, max: null };
  return { id, label, kind, value, ...range, source, locked: lock !== undefined, lock_reason: lock ?? null };
}

/** The llama.cpp server status with nothing set and nothing running. */
export const SERVER_STOPPED: LlamacppServerStatus = {
  status: "ok",
  state: "stopped",
  reason: null,
  exit_code: null,
  pid_running: false,
  running_with: null,
  pending_restart: false,
  saved: {
    binary: serverField("server_binary", "Program path", "text", ""),
    model: serverField("server_model", "Model", "text", ""),
    context_window: serverField("context_window", "Context window (tokens)", "int", 16384),
    idle_sleep: { ...serverField("idle_sleep", "Idle sleep (seconds)", "int", 300), min: 0, max: 86400 },
  },
};

/** A server status built from the stopped one with changed parts. */
export function serverStatus(change: Partial<LlamacppServerStatus>, saved: Partial<Record<"binary" | "model" | "context_window" | "idle_sleep", Partial<ServerField>>> = {}): LlamacppServerStatus {
  const merged = { ...SERVER_STOPPED.saved };
  for (const key of ["binary", "model", "context_window", "idle_sleep"] as const) merged[key] = { ...merged[key], ...saved[key] };
  return { ...SERVER_STOPPED, ...change, saved: merged };
}

export const OLLAMA: Connection = {
  provider: "ollama",
  display_name: "Ollama",
  locality: "local",
  installed: true,
  install_hint: null,
  fields: [urlField("base_url", "Address", "http://127.0.0.1:11434")],
  read_only: [{ label: "Answer model", value: "qwen3" }],
  roles: ["answers", "metadata"],
};

export const LLAMACPP: Connection = {
  provider: "llamacpp",
  display_name: "llama.cpp",
  locality: "local",
  installed: true,
  install_hint: null,
  fields: [urlField("chat_url", "Chat address", "http://127.0.0.1:8082/v1")],
  read_only: [
    { label: "Embedding address", value: "http://127.0.0.1:8081/v1" },
    { label: "Embedding model", value: "bge-small" },
  ],
  roles: ["embeddings"],
};

export const OPENROUTER: Connection = {
  provider: "openrouter",
  display_name: "OpenRouter",
  locality: "cloud",
  installed: true,
  install_hint: null,
  fields: [
    { id: "api_key", label: "API key", kind: "secret", source: "keychain", ...NO_KEY, set: true, last4: "wxyz", saved_at: "2026-10-14T10:00:00Z" },
  ],
  read_only: [{ label: "Verification model", value: "openai/gpt-5-mini" }],
  roles: ["verification"],
};

export const CONNECTIONS: ConnectionList = { status: "ok", config_dir: CONFIG_DIR, user_config_dir: "~/.config/omrg", keychain: "available", connections: [OLLAMA, LLAMACPP, OPENROUTER] };

export const CHAT_READY: ChatSettings = {
  status: "ok",
  provider: "ollama",
  model: "qwen3:4b",
  source: "saved",
  locked: false,
  lock_reason: null,
  enabled: true,
  ready: true,
  reason: null,
};

export const MCP_OFF: McpState = {
  status: "ok",
  enabled: false,
  url: "http://127.0.0.1:8765/mcp",
  token: { exists: false, created_at: null },
};

export const WEB_PORT: WebPortState = { status: "ok", saved: null, bound: 8765 };

export function logRecord(seq: number, level: LogRecord["level"], message: string, logger = "omrg.server"): LogRecord {
  return { seq, time: `2026-10-14T09:30:${String(seq).padStart(2, "0")}Z`, level, logger, message };
}

/** The documents server plus a default answer for every route Settings reads. */
export function settingsServer(handlers: Record<string, Handler> = {}) {
  return documentsServer({
    "GET /v1/health": () => ({ status: "ok", ready: true, version: "2.0.0" }),
    "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: ["files", "graph", "read", "run"], workspace: "/home/u/.omrg/workspace" }),
    "GET /v1/pipeline-operations": () => ({
      status: "ok",
      operations: [
        { operation_id: "retrieve.dense", title: "Dense retrieval", available: true, capabilities: [] },
        { operation_id: "rerank.cross_encoder", title: "Cross-encoder rerank", available: false, capabilities: ["reranker"] },
      ],
    }),
    "GET /v1/connections": () => CONNECTIONS,
    "GET /v1/llamacpp/server": () => SERVER_STOPPED,
    "GET /v1/settings/chat": () => CHAT_READY,
    "GET /v1/logs": () => ({ status: "ok", records: [], last_seq: 0 }),
    "GET /v1/mcp": () => MCP_OFF,
    "GET /v1/settings/web-port": () => WEB_PORT,
    ...handlers,
  });
}
