import { useQuery } from "@tanstack/react-query";
import { act, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useApi } from "../api/ApiProvider";
import { runQuery, runsQuery } from "../api/queries";
import { renderHookWithProviders } from "../test/providers";
import { useRunMonitor } from "./useRunMonitor";
import { event, eventSourceFactory, FakeEventSource } from "./test/fakes";
import { runServer } from "./test/runServer";

function reads(server: ReturnType<typeof runServer>, path: string) {
  return server.calls.filter((call) => call.method === "GET" && call.path === path).length;
}

function mount() {
  const server = runServer();
  const eventSource = eventSourceFactory();
  const view = renderHookWithProviders(
    () => {
      const api = useApi();
      return { list: useQuery(runsQuery(api, {})), run: useQuery(runQuery(api, "r2")), monitor: useRunMonitor("r2", { eventSource }) };
    },
    { fetchImpl: server.fetchImpl },
  );
  return { server, ...view };
}

describe("useRunMonitor and the query cache", () => {
  it("leaves the run queries alone while events arrive", async () => {
    const { server, result } = mount();
    await waitFor(() => expect(result.current.run.isSuccess && result.current.list.isSuccess).toBe(true));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    act(() => {
      FakeEventSource.latest().open();
      FakeEventSource.latest().send(event(3, "node_started", { run_id: "r2", node_id: "dense" }));
    });
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(reads(server, "/v1/runs")).toBe(1);
  });

  it("invalidates the run list and the run when the stream reports a terminal event", async () => {
    const { server, result } = mount();
    await waitFor(() => expect(result.current.run.isSuccess && result.current.list.isSuccess).toBe(true));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const runReadsBefore = reads(server, "/v1/runs/r2");
    act(() => {
      FakeEventSource.latest().open();
      FakeEventSource.latest().frame("run.end", { status: "succeeded" });
    });
    await waitFor(() => expect(reads(server, "/v1/runs")).toBe(2));
    await waitFor(() => expect(reads(server, "/v1/runs/r2")).toBeGreaterThan(runReadsBefore));
  });
});
