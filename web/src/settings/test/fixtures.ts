import type { Connection, ConnectionList, LogRecord, McpState, WebPortState } from "../../api/settings";
import { documentsServer, type Handler } from "../../test/fakeDocumentsServer";

/** Fixtures built from the `openapi.yaml` schemas for the Settings routes. */
export const CONFIG_DIR = "/srv/omrg project";

export const OLLAMA: Connection = {
  provider: "ollama",
  urls: [{ label: "base", url: "http://127.0.0.1:11434" }],
  models: [
    { label: "chat", name: "llama3.2" },
    { label: "answers", name: "qwen3" },
  ],
  key_set: false,
  roles: ["answers", "metadata"],
};

export const LLAMACPP: Connection = {
  provider: "llamacpp",
  urls: [
    { label: "embeddings", url: "http://127.0.0.1:8081/v1" },
    { label: "chat", url: "http://127.0.0.1:8082/v1" },
  ],
  models: [{ label: "embeddings", name: "bge-small" }],
  key_set: false,
  roles: ["embeddings"],
};

export const OPENROUTER: Connection = {
  provider: "openrouter",
  urls: [{ label: "base", url: "https://openrouter.ai/api/v1" }],
  models: [{ label: "verification", name: "openai/gpt-5-mini" }],
  key_set: true,
  roles: ["verification"],
};

export const CONNECTIONS: ConnectionList = { status: "ok", config_dir: CONFIG_DIR, connections: [OLLAMA, LLAMACPP, OPENROUTER] };

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
    "GET /v1/logs": () => ({ status: "ok", records: [], last_seq: 0 }),
    "GET /v1/mcp": () => MCP_OFF,
    "GET /v1/settings/web-port": () => WEB_PORT,
    ...handlers,
  });
}
