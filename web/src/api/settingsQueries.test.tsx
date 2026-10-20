import { useQuery } from "@tanstack/react-query";
import { waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { documentsServer } from "../test/fakeDocumentsServer";
import { renderHookWithProviders } from "../test/providers";
import { useApi } from "./ApiProvider";
import { connectionsQuery, healthQuery, mcpQuery, queryKeys, uploadLimitQuery, webPortQuery } from "./queries";

describe("settings query keys", () => {
  it("use the keys the design names", () => {
    expect(queryKeys.connections()).toEqual(["connections"]);
    expect(queryKeys.mcp()).toEqual(["mcp"]);
    expect(queryKeys.webPort()).toEqual(["settings", "web-port"]);
    expect(queryKeys.uploadLimit()).toEqual(["settings", "upload-limit"]);
    expect(queryKeys.documentReading()).toEqual(["settings", "document-reading"]);
    expect(queryKeys.health()).toEqual(["health"]);
  });
});

describe("settings queries", () => {
  it("read connections from GET /v1/connections and cache them under [connections]", async () => {
    const server = documentsServer({ "GET /v1/connections": () => ({ status: "ok", config_dir: "/srv/omrg", connections: [] }) });
    const { result } = renderHookWithProviders(() => useQuery(connectionsQuery(useApi())), { fetchImpl: server.fetchImpl });
    await waitFor(() => expect(result.current.data?.config_dir).toBe("/srv/omrg"));
    expect(server.calls.map((call) => call.path)).toEqual(["/v1/connections"]);
  });

  it("read health, the MCP state and the web port", async () => {
    const server = documentsServer({
      "GET /v1/health": () => ({ status: "ok", ready: true, version: "2.0.0" }),
      "GET /v1/mcp": () => ({ status: "ok", enabled: true, url: "http://127.0.0.1:8765/mcp", token: { exists: false, created_at: null } }),
      "GET /v1/settings/web-port": () => ({ status: "ok", saved: 9000, bound: 8765 }),
    });
    const { result } = renderHookWithProviders(
      () => {
        const api = useApi();
        return [useQuery(healthQuery(api)), useQuery(mcpQuery(api)), useQuery(webPortQuery(api))] as const;
      },
      { fetchImpl: server.fetchImpl },
    );
    await waitFor(() => expect(result.current.every((query) => query.isSuccess)).toBe(true));
    expect(result.current[0].data?.ready).toBe(true);
    expect(result.current[1].data?.url).toBe("http://127.0.0.1:8765/mcp");
    expect(result.current[2].data?.saved).toBe(9000);
  });

  it("reads the upload limit from GET /v1/settings/upload-limit", async () => {
    const server = documentsServer({
      "GET /v1/settings/upload-limit": () => ({ status: "ok", max_bytes: 104857600, source: "config-file", saved_mib: 100, default_mib: 50, min_mib: 1, max_mib: 2048 }),
    });
    const { result } = renderHookWithProviders(() => useQuery(uploadLimitQuery(useApi())), { fetchImpl: server.fetchImpl });
    await waitFor(() => expect(result.current.data?.saved_mib).toBe(100));
    expect(server.calls.map((call) => call.path)).toEqual(["/v1/settings/upload-limit"]);
  });
});
