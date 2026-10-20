import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { MCP_OFF, settingsServer } from "../settings/test/fixtures";
import { ApiProvider, useApi } from "./ApiProvider";
import { createQueryClient, queryKeys, uploadLimitQuery } from "./queries";
import {
  useRemoveProviderKey,
  useRevokeMcpToken,
  useRotateMcpToken,
  useSaveProviderFields,
  useSaveProviderKey,
  useSetChatSettings,
  useSetJudgeSettings,
  useSetMcpEnabled,
  useSetUploadLimit,
  useSetWebPort,
} from "./settingsMutations";

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

describe("settings mutations", () => {
  it("writes the MCP state the server returned into the cache", async () => {
    const { wrapper, queryClient } = setup({ "PUT /v1/mcp": () => ({ ...MCP_OFF, enabled: true }) });
    const { result } = renderHook(() => useSetMcpEnabled(), { wrapper });
    act(() => result.current.mutate(true));
    await waitFor(() => expect(queryClient.getQueryData(queryKeys.mcp())).toMatchObject({ enabled: true }));
  });

  it("refreshes the MCP state after a token is created or revoked", async () => {
    const { wrapper, queryClient, server } = setup({
      "POST /v1/mcp/token": () => ({ status: "ok", token: "omrg_mcp_x", created_at: "2026-10-14T10:00:00Z" }),
      "DELETE /v1/mcp/token": () => ({ status: "ok", revoked: true }),
    });
    await queryClient.prefetchQuery({ queryKey: queryKeys.mcp(), queryFn: () => MCP_OFF });
    const rotate = renderHook(() => useRotateMcpToken(), { wrapper });
    const revoke = renderHook(() => useRevokeMcpToken(), { wrapper });
    act(() => rotate.result.current.mutate());
    await waitFor(() => expect(queryClient.getQueryState(queryKeys.mcp())?.isInvalidated).toBe(true));
    await queryClient.refetchQueries({ queryKey: queryKeys.mcp() }).catch(() => undefined);
    act(() => revoke.result.current.mutate());
    await waitFor(() => expect(server.find("DELETE", "/v1/mcp/token")).toHaveLength(1));
  });

  it("writes the saved web port the server returned into the cache", async () => {
    const { wrapper, queryClient } = setup({ "PUT /v1/settings/web-port": () => ({ status: "ok", saved: 9100, bound: 8765 }) });
    const { result } = renderHook(() => useSetWebPort(), { wrapper });
    act(() => result.current.mutate(9100));
    await waitFor(() => expect(queryClient.getQueryData(queryKeys.webPort())).toEqual({ status: "ok", saved: 9100, bound: 8765 }));
  });

  it("refreshes the upload limit after a save, so every view reads the new limit", async () => {
    let saved: number | null = null;
    const state = () => ({ status: "ok", max_bytes: (saved ?? 50) * 1048576, source: saved === null ? "default" : "config-file", saved_mib: saved, default_mib: 50, min_mib: 1, max_mib: 2048 });
    const { wrapper, queryClient, server } = setup({
      "GET /v1/settings/upload-limit": state,
      "PUT /v1/settings/upload-limit": (body: Record<string, unknown>) => {
        saved = body.max_mib as number | null;
        return state();
      },
    });
    const limit = renderHook(() => useQuery({ ...uploadLimitQuery(useApi()) }), { wrapper });
    await waitFor(() => expect(limit.result.current.data?.saved_mib).toBeNull());
    const { result } = renderHook(() => useSetUploadLimit(), { wrapper });
    act(() => result.current.mutate(200));
    await waitFor(() => expect(limit.result.current.data?.max_bytes).toBe(200 * 1048576));
    expect(server.find("GET", "/v1/settings/upload-limit")).toHaveLength(2);
    expect(queryClient.getQueryData(queryKeys.uploadLimit())).toMatchObject({ saved_mib: 200 });
  });

  it("refreshes the connections and the Chat status after a provider write", async () => {
    const ok = () => ({ status: "ok" });
    const { wrapper, queryClient, server } = setup({
      "PUT /v1/connections/ollama": ok,
      "PUT /v1/connections/openrouter/key": ok,
      "DELETE /v1/connections/openrouter/key": ok,
    });
    const fields = renderHook(() => useSaveProviderFields("ollama"), { wrapper });
    const key = renderHook(() => useSaveProviderKey("openrouter"), { wrapper });
    const remove = renderHook(() => useRemoveProviderKey("openrouter"), { wrapper });
    for (const run of [() => fields.result.current.mutate({ base_url: "http://gpu:11434" }), () => key.result.current.mutate("sk-or-typed-0001"), () => remove.result.current.mutate()]) {
      await queryClient.prefetchQuery({ queryKey: queryKeys.connections(), queryFn: () => ({}) });
      await queryClient.prefetchQuery({ queryKey: queryKeys.chatSettings(), queryFn: () => ({}) });
      act(run);
      await waitFor(() => expect(queryClient.getQueryState(queryKeys.connections())?.isInvalidated).toBe(true));
      expect(queryClient.getQueryState(queryKeys.chatSettings())?.isInvalidated).toBe(true);
    }
    expect(server.calls.filter((call) => call.method !== "GET")).toHaveLength(3);
  });

  it("refreshes the Chat status after a save or a clear", async () => {
    const { wrapper, queryClient, server } = setup({ "PUT /v1/settings/chat": () => ({ status: "ok" }) });
    await queryClient.prefetchQuery({ queryKey: queryKeys.chatSettings(), queryFn: () => ({}) });
    const { result } = renderHook(() => useSetChatSettings(), { wrapper });
    act(() => result.current.mutate(null));
    await waitFor(() => expect(queryClient.getQueryState(queryKeys.chatSettings())?.isInvalidated).toBe(true));
    expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(1);
  });
  it("refreshes the judge status after a save or a clear", async () => {
    const { wrapper, queryClient, server } = setup({ "PUT /v1/settings/judge": () => ({ status: "ok", revision: "r2" }) });
    await queryClient.prefetchQuery({ queryKey: queryKeys.judgeSettings(), queryFn: () => ({}) });
    const { result } = renderHook(() => useSetJudgeSettings(), { wrapper });
    act(() => result.current.mutate({ provider: "openrouter", model: "openai/gpt-5-mini" }));
    await waitFor(() => expect(queryClient.getQueryState(queryKeys.judgeSettings())?.isInvalidated).toBe(true));
    expect(server.find("PUT", "/v1/settings/judge")).toHaveLength(1);
  });

  it("refreshes the judge status after a provider write, because a key can make the judge ready", async () => {
    const { wrapper, queryClient } = setup({ "PUT /v1/connections/openrouter/key": () => ({ status: "ok" }) });
    await queryClient.prefetchQuery({ queryKey: queryKeys.judgeSettings(), queryFn: () => ({}) });
    const { result } = renderHook(() => useSaveProviderKey("openrouter"), { wrapper });
    act(() => result.current.mutate("sk-or-typed-0001"));
    await waitFor(() => expect(queryClient.getQueryState(queryKeys.judgeSettings())?.isInvalidated).toBe(true));
  });
});
