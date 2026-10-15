import { describe, expect, it } from "vitest";
import { createApiClient } from "./client";
import {
  getConnections,
  getHealth,
  getLogs,
  getMcpState,
  getUploadLimit,
  getWebPort,
  LOG_STREAM_PATH,
  revokeMcpToken,
  rotateMcpToken,
  setMcpEnabled,
  setUploadLimit,
  setWebPort,
  testConnection,
} from "./settings";
import { documentsServer } from "../test/fakeDocumentsServer";

const CONNECTIONS = {
  status: "ok",
  config_dir: "/srv/omrg",
  connections: [
    {
      provider: "ollama",
      urls: [{ label: "base", url: "http://127.0.0.1:11434" }],
      models: [{ label: "embeddings", name: "nomic-embed-text" }],
      key_set: false,
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
    const state = { status: "ok", enabled: false, url: "http://127.0.0.1:8765/mcp", token: { exists: false, created_at: null } };
    const { api, server } = setup({
      "GET /v1/mcp": () => state,
      "PUT /v1/mcp": (body) => ({ ...state, enabled: body.enabled }),
    });
    await expect(getMcpState(api)).resolves.toMatchObject({ enabled: false });
    await expect(setMcpEnabled(api, true)).resolves.toMatchObject({ enabled: true });
    expect(server.find("PUT", "/v1/mcp")[0]?.body).toEqual({ enabled: true });
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
    await setWebPort(api, null);
    expect(server.find("PUT", "/v1/settings/web-port").map((call) => call.body)).toEqual([{ port: 9000 }, { port: null }]);
  });

  it("reads and saves the upload limit, and returns to the default with null", async () => {
    const state = { status: "ok", max_bytes: 52428800, source: "default", saved_mib: null, default_mib: 50, min_mib: 1, max_mib: 2048 };
    const { api, server } = setup({
      "GET /v1/settings/upload-limit": () => state,
      "PUT /v1/settings/upload-limit": (body) => ({ ...state, saved_mib: body.max_mib, source: body.max_mib === null ? "default" : "saved" }),
    });
    await expect(getUploadLimit(api)).resolves.toEqual(state);
    await expect(setUploadLimit(api, 200)).resolves.toMatchObject({ saved_mib: 200, source: "saved" });
    await setUploadLimit(api, null);
    expect(server.find("PUT", "/v1/settings/upload-limit").map((call) => call.body)).toEqual([{ max_mib: 200 }, { max_mib: null }]);
    expect(server.find("GET", "/v1/settings/upload-limit")).toHaveLength(1);
  });
});
