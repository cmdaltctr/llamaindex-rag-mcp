import { describe, expect, it } from "vitest";
import { createApiClient } from "./client";
import {
  getChatSettings,
  getConnections,
  getHealth,
  getLogs,
  getMcpState,
  getUploadLimit,
  getWebPort,
  listProviderModels,
  LOG_STREAM_PATH,
  removeProviderKey,
  revokeMcpToken,
  rotateMcpToken,
  saveProviderFields,
  saveProviderKey,
  setChatSettings,
  setMcpEnabled,
  setUploadLimit,
  setWebPort,
  testChatModel,
  testConnection,
} from "./settings";
import { documentsServer } from "../test/fakeDocumentsServer";

const CONNECTIONS = {
  status: "ok",
  config_dir: "/srv/omrg",
  keychain: "available",
  connections: [
    {
      provider: "ollama",
      display_name: "Ollama",
      locality: "local",
      installed: true,
      install_hint: null,
      fields: [],
      read_only: [],
      roles: ["embeddings", "answers"],
    },
  ],
};

function setup(handlers: Parameters<typeof documentsServer>[0]) {
  const server = documentsServer(handlers);
  return { server, api: createApiClient(server.fetchImpl) };
}

describe("settings API", () => {
  it("reads health", async () => {
    const { api } = setup({ "GET /v1/health": () => ({ status: "ok", ready: true, version: "2.0.0" }) });
    await expect(getHealth(api)).resolves.toEqual({ status: "ok", ready: true, version: "2.0.0" });
  });

  it("reads the connections and the config directory", async () => {
    const { api } = setup({ "GET /v1/connections": () => CONNECTIONS });
    const result = await getConnections(api);
    expect(result.config_dir).toBe("/srv/omrg");
    expect(result.connections[0]?.provider).toBe("ollama");
  });

  it("tests one provider with POST", async () => {
    const { api, server } = setup({ "POST /v1/connections/openrouter/test": () => ({ status: "ok", reachable: false, reason: "unauthorised" }) });
    await expect(testConnection(api, "openrouter")).resolves.toMatchObject({ reachable: false, reason: "unauthorised" });
    expect(server.find("POST", "/v1/connections/openrouter/test")).toHaveLength(1);
    expect(server.calls[0]?.body).toEqual({ fields: {} });
  });

  it("sends typed values with the test and the model list", async () => {
    const { api, server } = setup({
      "POST /v1/connections/ollama/test": () => ({ status: "ok", reachable: true, reason: null }),
      "POST /v1/connections/ollama/models": () => ({ status: "ok", reachable: true, reason: null, models: ["qwen3:4b"], truncated: false }),
    });
    await testConnection(api, "ollama", { base_url: "http://gpu:11434" });
    await expect(listProviderModels(api, "ollama", { base_url: "http://gpu:11434" })).resolves.toMatchObject({ models: ["qwen3:4b"] });
    expect(server.calls.map((call) => call.body)).toEqual([{ fields: { base_url: "http://gpu:11434" } }, { fields: { base_url: "http://gpu:11434" } }]);
  });

  it("saves addresses and keys with PUT and removes a key with DELETE", async () => {
    const ok = () => ({ status: "ok" });
    const { api, server } = setup({
      "PUT /v1/connections/ollama": ok,
      "PUT /v1/connections/openrouter/key": ok,
      "DELETE /v1/connections/openrouter/key": ok,
    });
    await saveProviderFields(api, "ollama", { base_url: null });
    await saveProviderKey(api, "openrouter", "sk-or-typed-0001");
    await removeProviderKey(api, "openrouter");
    expect(server.calls.map((call) => [call.method, call.path, call.body])).toEqual([
      ["PUT", "/v1/connections/ollama", { fields: { base_url: null } }],
      ["PUT", "/v1/connections/openrouter/key", { api_key: "sk-or-typed-0001" }],
      ["DELETE", "/v1/connections/openrouter/key", null],
    ]);
  });

  it("carries the revision on every provider write", async () => {
    const ok = () => ({ status: "ok", revision: "r2" });
    const { api, server } = setup({
      "PUT /v1/connections/ollama": ok,
      "PUT /v1/connections/openrouter/key": ok,
      "DELETE /v1/connections/openrouter/key": ok,
    });
    const options = { revision: "r1" };
    await saveProviderFields(api, "ollama", { base_url: null }, options);
    await saveProviderKey(api, "openrouter", "sk-or-typed-0001", options);
    await removeProviderKey(api, "openrouter", options);
    expect(server.calls.map((call) => call.body)).toEqual([
      { fields: { base_url: null }, revision: "r1" },
      { api_key: "sk-or-typed-0001", revision: "r1" },
      { revision: "r1" },
    ]);
  });

  it("reads, saves and tests the Chat choice", async () => {
    const { api, server } = setup({
      "GET /v1/settings/chat": () => ({ status: "ok", provider: null, model: null, source: "default", locked: false, lock_reason: null, enabled: true, ready: false, reason: "not-configured" }),
      "PUT /v1/settings/chat": () => ({ status: "ok" }),
      "POST /v1/settings/chat/test": () => ({ status: "ok", ok: true, reason: null, elapsed_ms: 40 }),
    });
    await expect(getChatSettings(api)).resolves.toMatchObject({ ready: false, reason: "not-configured" });
    await setChatSettings(api, { provider: "ollama", model: "qwen3:4b" });
    await setChatSettings(api, null);
    await expect(testChatModel(api, { provider: "ollama", model: "qwen3:4b" })).resolves.toMatchObject({ ok: true, elapsed_ms: 40 });
    await testChatModel(api);
    expect(server.calls.slice(1).map((call) => call.body)).toEqual([{ provider: "ollama", model: "qwen3:4b" }, null, { provider: "ollama", model: "qwen3:4b" }, {}]);
  });

  it("carries the revision on a Chat save and on a clear", async () => {
    const { api, server } = setup({ "PUT /v1/settings/chat": () => ({ status: "ok", revision: "r2" }) });
    await setChatSettings(api, { provider: "ollama", model: "qwen3:4b" }, { revision: "r1" });
    await setChatSettings(api, null, { revision: "r1" });
    expect(server.calls.map((call) => call.body)).toEqual([{ provider: "ollama", model: "qwen3:4b", revision: "r1" }, { revision: "r1" }]);
  });

  it("reads logs after a sequence", async () => {
    const { api, server } = setup({ "GET /v1/logs": () => ({ status: "ok", records: [], last_seq: 7 }) });
    await expect(getLogs(api, 5)).resolves.toEqual({ status: "ok", records: [], last_seq: 7 });
    expect(server.calls[0]?.path).toBe("/v1/logs?after=5");
  });

  it("names the log stream path", () => {
    expect(LOG_STREAM_PATH).toBe("/v1/logs/stream");
  });

  it("reads and sets the MCP switch with the body the contract names", async () => {
    const state = { status: "ok", revision: "r1", enabled: false, source: "default", url: "http://127.0.0.1:8765/mcp", token: { exists: false, created_at: null } };
    const { api, server } = setup({
      "GET /v1/mcp": () => state,
      "PUT /v1/mcp": (body) => ({ ...state, enabled: body.enabled }),
    });
    await expect(getMcpState(api)).resolves.toMatchObject({ enabled: false });
    await expect(setMcpEnabled(api, true)).resolves.toMatchObject({ enabled: true });
    expect(server.find("PUT", "/v1/mcp")[0]?.body).toEqual({ enabled: true });
    await setMcpEnabled(api, false, { revision: "r1" });
    expect(server.find("PUT", "/v1/mcp")[1]?.body).toEqual({ enabled: false, revision: "r1" });
  });

  it("creates and revokes the MCP token", async () => {
    const { api, server } = setup({
      "POST /v1/mcp/token": () => ({ status: "ok", token: "omrg_mcp_abc", created_at: "2026-10-14T10:00:00Z" }),
      "DELETE /v1/mcp/token": () => ({ status: "ok", revoked: true }),
    });
    await expect(rotateMcpToken(api)).resolves.toMatchObject({ token: "omrg_mcp_abc" });
    await expect(revokeMcpToken(api)).resolves.toMatchObject({ revoked: true });
    expect(server.calls.map((call) => call.method)).toEqual(["POST", "DELETE"]);
  });

  it("reads and saves the web port, and clears it with null", async () => {
    const { api, server } = setup({
      "GET /v1/settings/web-port": () => ({ status: "ok", saved: null, bound: 8765 }),
      "PUT /v1/settings/web-port": (body) => ({ status: "ok", saved: body.port, bound: 8765 }),
    });
    await expect(getWebPort(api)).resolves.toEqual({ status: "ok", saved: null, bound: 8765 });
    await setWebPort(api, 9000);
    await setWebPort(api, null, { revision: "r1" });
    expect(server.find("PUT", "/v1/settings/web-port").map((call) => call.body)).toEqual([{ port: 9000 }, { port: null, revision: "r1" }]);
  });

  it("reads and saves the upload limit, and returns to the default with null", async () => {
    const state = { status: "ok", max_bytes: 52428800, source: "default", saved_mib: null, default_mib: 50, min_mib: 1, max_mib: 2048 };
    const { api, server } = setup({
      "GET /v1/settings/upload-limit": () => state,
      "PUT /v1/settings/upload-limit": (body) => ({ ...state, saved_mib: body.max_mib, source: body.max_mib === null ? "default" : "config-file" }),
    });
    await expect(getUploadLimit(api)).resolves.toEqual(state);
    await expect(setUploadLimit(api, 200)).resolves.toMatchObject({ saved_mib: 200, source: "config-file" });
    await setUploadLimit(api, null, { revision: "r1" });
    expect(server.find("PUT", "/v1/settings/upload-limit").map((call) => call.body)).toEqual([{ max_mib: 200 }, { max_mib: null, revision: "r1" }]);
    expect(server.find("GET", "/v1/settings/upload-limit")).toHaveLength(1);
  });
});
