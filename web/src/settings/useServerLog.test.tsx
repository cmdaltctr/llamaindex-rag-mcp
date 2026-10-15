import { act, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { json } from "../test/fakeDocumentsServer";
import { FakeEventSource } from "../test/fakeEventSource";
import { renderHookWithProviders } from "../test/providers";
import { logRecord, settingsServer } from "./test/fixtures";
import { MAX_LOG_RECORDS, useServerLog } from "./useServerLog";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeEventSource.reset();
});

function withStream() {
  FakeEventSource.reset();
  vi.stubGlobal("EventSource", FakeEventSource);
}

describe("useServerLog", () => {
  it("loads the buffered records, then follows the stream from the last sequence", async () => {
    withStream();
    const server = settingsServer({
      "GET /v1/logs": () => ({ status: "ok", records: [logRecord(1, "info", "one"), logRecord(2, "warning", "two")], last_seq: 2 }),
    });
    const { result } = renderHookWithProviders(() => useServerLog(), { fetchImpl: server.fetchImpl });
    await waitFor(() => expect(result.current.records.map((r) => r.message)).toEqual(["one", "two"]));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    expect(FakeEventSource.latest().url).toBe("/v1/logs/stream?after=2");
    act(() => FakeEventSource.latest().open());
    expect(result.current.mode).toBe("streaming");
  });

  it("appends a live record and drops one it already has", async () => {
    withStream();
    const server = settingsServer();
    const { result } = renderHookWithProviders(() => useServerLog(), { fetchImpl: server.fetchImpl });
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    act(() => {
      FakeEventSource.latest().frame("log", logRecord(1, "error", "boom"), 1);
      FakeEventSource.latest().frame("log", logRecord(1, "error", "boom"), 1);
      FakeEventSource.latest().frame("log", logRecord(2, "info", "next"), 2);
    });
    expect(result.current.records.map((r) => r.seq)).toEqual([1, 2]);
  });

  it("keeps at most 1,000 records in memory", async () => {
    withStream();
    const many = Array.from({ length: MAX_LOG_RECORDS + 100 }, (_, i) => logRecord(i + 1, "info", `m${i + 1}`));
    const server = settingsServer({ "GET /v1/logs": () => ({ status: "ok", records: many, last_seq: many.length }) });
    const { result } = renderHookWithProviders(() => useServerLog(), { fetchImpl: server.fetchImpl });
    await waitFor(() => expect(result.current.records).toHaveLength(MAX_LOG_RECORDS));
    expect(result.current.records[0]?.seq).toBe(101);
    expect(result.current.records.at(-1)?.seq).toBe(MAX_LOG_RECORDS + 100);
  });

  it("stops following when the server says it is closing", async () => {
    withStream();
    const { result } = renderHookWithProviders(() => useServerLog(), { fetchImpl: settingsServer().fetchImpl });
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    act(() => FakeEventSource.latest().frame("server.closing", { reason: "shutdown" }));
    expect(result.current.mode).toBe("ended");
    expect(FakeEventSource.latest().readyState).toBe(2);
  });

  it("shows reconnecting while the browser retries, and polls when the stream is refused", async () => {
    withStream();
    let polls = 0;
    const server = settingsServer({
      "GET /v1/logs": (_body, call) => {
        if (call.path.includes("after=0") && polls === 0) {
          polls += 1;
          return { status: "ok", records: [], last_seq: 0 };
        }
        return { status: "ok", records: [logRecord(1, "warning", "from poll")], last_seq: 1 };
      },
    });
    const { result } = renderHookWithProviders(() => useServerLog({ pollMs: 10 }), { fetchImpl: server.fetchImpl });
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    act(() => FakeEventSource.latest().fail(false));
    expect(result.current.mode).toBe("reconnecting");
    act(() => FakeEventSource.latest().fail(true));
    await waitFor(() => expect(result.current.records.map((r) => r.message)).toEqual(["from poll"]));
    expect(result.current.mode).toBe("polling");
  });

  it("polls GET /v1/logs?after= when EventSource is not available", async () => {
    expect(typeof EventSource).toBe("undefined");
    let call = 0;
    const server = settingsServer({
      "GET /v1/logs": () => {
        call += 1;
        return call === 1
          ? { status: "ok", records: [logRecord(1, "info", "first")], last_seq: 1 }
          : { status: "ok", records: [logRecord(2, "info", "second")], last_seq: 2 };
      },
    });
    const { result } = renderHookWithProviders(() => useServerLog({ pollMs: 10 }), { fetchImpl: server.fetchImpl });
    await waitFor(() => expect(result.current.records.map((r) => r.message)).toEqual(["first", "second"]));
    expect(result.current.mode).toBe("polling");
    expect(server.calls.map((c) => c.path)).toContain("/v1/logs?after=1");
  });

  it("reports a failed first load and loads again on retry", async () => {
    withStream();
    let fail = true;
    const server = settingsServer({
      "GET /v1/logs": () => (fail ? json({ status: "error", message: "boom" }, 500) : { status: "ok", records: [logRecord(1, "info", "ok")], last_seq: 1 }),
    });
    const { result } = renderHookWithProviders(() => useServerLog(), { fetchImpl: server.fetchImpl });
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.mode).toBe("error");
    fail = false;
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.records).toHaveLength(1));
    expect(result.current.error).toBeNull();
  });

  it("closes the stream when it unmounts", async () => {
    withStream();
    const { unmount } = renderHookWithProviders(() => useServerLog(), { fetchImpl: settingsServer().fetchImpl });
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    unmount();
    expect(FakeEventSource.latest().readyState).toBe(2);
  });
});
