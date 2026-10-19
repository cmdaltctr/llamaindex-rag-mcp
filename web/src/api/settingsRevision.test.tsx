import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { settingsServer } from "../settings/test/fixtures";
import { ApiProvider, useApi } from "./ApiProvider";
import { chatSettingsQuery, connectionsQuery, createQueryClient, mcpQuery, uploadLimitQuery, webPortQuery } from "./queries";
import { currentRevision, reloadSettings, rememberRevision } from "./settingsRevision";
import { useSaveProviderFields, useSetChatSettings, useSetMcpEnabled, useSetUploadLimit, useSetWebPort } from "./settingsMutations";

function setup(handlers = {}) {
  const server = settingsServer(handlers);
  const queryClient = createQueryClient({ retry: false });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ApiProvider fetchImpl={server.fetchImpl}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ApiProvider>
  );
  return { server, queryClient, wrapper };
}

describe("settings revision", () => {
  it("remembers the revision of any response that holds one", () => {
    const { queryClient } = setup();
    expect(currentRevision(queryClient)).toBeUndefined();
    rememberRevision(queryClient, { status: "ok", revision: "r1" });
    expect(currentRevision(queryClient)).toBe("r1");
    rememberRevision(queryClient, { status: "ok" });
    rememberRevision(queryClient, null);
    expect(currentRevision(queryClient)).toBe("r1");
  });

  it("takes the revision from each settings read", async () => {
    const { queryClient, wrapper } = setup();
    const connections = renderHook(() => useQuery(connectionsQuery(useApi())), { wrapper });
    await waitFor(() => expect(connections.result.current.data).toBeDefined());
    expect(currentRevision(queryClient)).toBe("r1");
    for (const make of [chatSettingsQuery, mcpQuery, webPortQuery, uploadLimitQuery]) {
      queryClient.removeQueries({ queryKey: ["settings-revision"] });
      const read = renderHook(() => useQuery(make(useApi()) as never), { wrapper });
      await waitFor(() => expect(read.result.current.isSuccess).toBe(true));
      expect(currentRevision(queryClient)).toBe("r1");
    }
  });

  it.each([
    ["address save", "PUT /v1/connections/ollama", () => useSaveProviderFields("ollama"), (m: ReturnType<typeof useSaveProviderFields>) => m.mutate({ base_url: "http://gpu:11434" }), { fields: { base_url: "http://gpu:11434" }, revision: "r1" }],
    ["Chat save", "PUT /v1/settings/chat", () => useSetChatSettings(), (m: ReturnType<typeof useSetChatSettings>) => m.mutate({ provider: "ollama", model: "qwen3:4b" }), { provider: "ollama", model: "qwen3:4b", revision: "r1" }],
    ["MCP switch", "PUT /v1/mcp", () => useSetMcpEnabled(), (m: ReturnType<typeof useSetMcpEnabled>) => m.mutate(true), { enabled: true, revision: "r1" }],
    ["web port", "PUT /v1/settings/web-port", () => useSetWebPort(), (m: ReturnType<typeof useSetWebPort>) => m.mutate(9100), { port: 9100, revision: "r1" }],
    ["upload limit", "PUT /v1/settings/upload-limit", () => useSetUploadLimit(), (m: ReturnType<typeof useSetUploadLimit>) => m.mutate(200), { max_mib: 200, revision: "r1" }],
  ])("sends the remembered revision with a %s and remembers the one that comes back", async (_name, route, hook, run, body) => {
    const { queryClient, wrapper, server } = setup({ [route]: () => ({ status: "ok", revision: "r2" }) });
    rememberRevision(queryClient, { revision: "r1" });
    const { result } = renderHook(hook as () => never, { wrapper });
    act(() => run(result.current as never));
    await waitFor(() => expect(currentRevision(queryClient)).toBe("r2"));
    expect(server.calls.filter((call) => call.method === "PUT")[0]?.body).toEqual(body);
  });

  it("sends no revision before the page has read one", async () => {
    const { wrapper, server, queryClient } = setup({ "PUT /v1/settings/web-port": () => ({ status: "ok", revision: "r2" }) });
    const { result } = renderHook(() => useSetWebPort(), { wrapper });
    act(() => result.current.mutate(9100));
    await waitFor(() => expect(currentRevision(queryClient)).toBe("r2"));
    expect(server.find("PUT", "/v1/settings/web-port")[0]?.body).toEqual({ port: 9100 });
  });

  it("refetches every settings read on reload and leaves other reads alone", async () => {
    const { queryClient, wrapper, server } = setup();
    const connections = renderHook(() => useQuery(connectionsQuery(useApi())), { wrapper });
    const health = renderHook(() => useQuery({ queryKey: ["health"], queryFn: () => ({ ok: true }) }), { wrapper });
    await waitFor(() => expect(connections.result.current.data).toBeDefined());
    await waitFor(() => expect(health.result.current.data).toBeDefined());
    expect(server.find("GET", "/v1/connections")).toHaveLength(1);
    await act(() => reloadSettings(queryClient));
    expect(server.find("GET", "/v1/connections")).toHaveLength(2);
    expect(queryClient.getQueryState(["health"])?.isInvalidated).toBe(false);
  });
});
