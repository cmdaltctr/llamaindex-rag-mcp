import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { serverStatus, settingsServer } from "../settings/test/fixtures";
import { ApiProvider } from "./ApiProvider";
import { llamacppServerKey, useLlamacppServer, useSaveLlamacppServer, useStartLlamacppServer } from "./llamacppServerHooks";
import { createQueryClient } from "./queries";
import { currentRevision, rememberRevision } from "./settingsRevision";

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

describe("llama.cpp server hooks", () => {
  it("reads the status", async () => {
    const { wrapper } = setup();
    const { result } = renderHook(() => useLlamacppServer(), { wrapper });
    await waitFor(() => expect(result.current.data?.state).toBe("stopped"));
  });

  it("puts the status a write returned into the cache", async () => {
    const { wrapper, queryClient } = setup({ "POST /v1/llamacpp/server/start": () => serverStatus({ state: "starting" }) });
    const { result } = renderHook(() => useStartLlamacppServer(), { wrapper });
    act(() => result.current.mutate());
    await waitFor(() => expect(queryClient.getQueryData(llamacppServerKey)).toMatchObject({ state: "starting" }));
  });

  it("sends a change and caches the answer", async () => {
    const { wrapper, queryClient, server } = setup({ "PUT /v1/llamacpp/server": () => serverStatus({}, { context_window: { value: 8192, source: "config-file" } }) });
    const { result } = renderHook(() => useSaveLlamacppServer(), { wrapper });
    act(() => result.current.mutate({ context_window: 8192 }));
    await waitFor(() => expect(queryClient.getQueryData(llamacppServerKey)).toMatchObject({ saved: { context_window: { value: 8192 } } }));
    expect(server.find("PUT", "/v1/llamacpp/server")[0]?.body).toEqual({ context_window: 8192 });
  });

  it("sends the remembered revision with a save and remembers the one that comes back", async () => {
    const { wrapper, queryClient, server } = setup({ "PUT /v1/llamacpp/server": () => ({ ...serverStatus({}), revision: "r2" }) });
    rememberRevision(queryClient, { revision: "r1" });
    const { result } = renderHook(() => useSaveLlamacppServer(), { wrapper });
    act(() => result.current.mutate({ model: "a/b" }));
    await waitFor(() => expect(currentRevision(queryClient)).toBe("r2"));
    expect(server.find("PUT", "/v1/llamacpp/server")[0]?.body).toEqual({ model: "a/b", revision: "r1" });
  });

  it("polls while the server is starting and stops when it runs", async () => {
    let reads = 0;
    const { wrapper } = setup({
      "GET /v1/llamacpp/server": () => {
        reads += 1;
        return serverStatus({ state: reads < 3 ? "starting" : "running" });
      },
    });
    const { result } = renderHook(() => useLlamacppServer(), { wrapper });
    await waitFor(() => expect(result.current.data?.state).toBe("running"), { timeout: 5000 });
    const seen = reads;
    await new Promise((resolve) => setTimeout(resolve, 1300));
    expect(reads).toBe(seen);
  });
});
