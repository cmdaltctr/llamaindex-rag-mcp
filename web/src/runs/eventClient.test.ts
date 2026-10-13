import { describe, expect, it, vi } from "vitest";
import type { RunEventRecord } from "../api/runs";
import { followRunEvents, type MonitorMode } from "./eventClient";
import { event, eventSourceFactory, FakeEventSource, json, manualScheduler } from "./test/fakes";

function recorder() {
  const events: RunEventRecord[] = [];
  const modes: MonitorMode[] = [];
  const ends: (string | null)[] = [];
  return {
    events,
    modes,
    ends,
    onEvent: (record: RunEventRecord) => events.push(record),
    onMode: (mode: MonitorMode) => modes.push(mode),
    onEnd: (info: { status: string | null }) => ends.push(info.status),
  };
}

function page(events: RunEventRecord[], complete = false, runStatus = "running") {
  const last = events.at(-1)?.sequence ?? 0;
  return json({ status: "ok", run_id: "r1", run_status: runStatus, events, last_sequence: last, complete });
}

describe("run event client: server-sent events", () => {
  it("opens the stream and delivers events in sequence order", () => {
    const factory = eventSourceFactory();
    const rec = recorder();
    followRunEvents({ runId: "r1", eventSource: factory, ...rec });
    const source = FakeEventSource.latest();
    expect(source.url).toBe("/v1/runs/r1/events/stream");
    source.open();
    source.send(event(1, "run.status", { summary: { status: "running" } }));
    source.send(event(2, "node_started", { node_id: "dense" }));
    expect(rec.events.map((e) => e.sequence)).toEqual([1, 2]);
    expect(rec.modes).toContain("streaming");
  });

  it("drops events that a reconnect replays again", () => {
    const factory = eventSourceFactory();
    const rec = recorder();
    followRunEvents({ runId: "r1", eventSource: factory, ...rec });
    const source = FakeEventSource.latest();
    source.open();
    source.send(event(1, "node_started", { node_id: "dense" }));
    source.send(event(2, "node_completed", { node_id: "dense" }));
    source.fail(false);
    expect(rec.modes.at(-1)).toBe("reconnecting");
    // The browser resends Last-Event-ID; the server may still repeat an event.
    source.open();
    source.send(event(2, "node_completed", { node_id: "dense" }));
    source.send(event(3, "node_started", { node_id: "rerank" }));
    expect(rec.events.map((e) => e.sequence)).toEqual([1, 2, 3]);
  });

  it("resumes a new stream after the last seen sequence", () => {
    const factory = eventSourceFactory();
    followRunEvents({ runId: "r1", afterSequence: 12, eventSource: factory, ...recorder() });
    expect(FakeEventSource.latest().url).toBe("/v1/runs/r1/events/stream?after=12");
  });

  it("stops on run.end and reports the terminal status", () => {
    const factory = eventSourceFactory();
    const rec = recorder();
    followRunEvents({ runId: "r1", eventSource: factory, ...rec });
    const source = FakeEventSource.latest();
    source.open();
    source.frame("run.end", { status: "succeeded", last_sequence: 9 });
    expect(source.readyState).toBe(2);
    expect(rec.ends).toEqual(["succeeded"]);
    expect(rec.modes.at(-1)).toBe("ended");
  });

  it("closes on server shutdown without claiming a run status", () => {
    const factory = eventSourceFactory();
    const rec = recorder();
    followRunEvents({ runId: "r1", eventSource: factory, ...rec });
    FakeEventSource.latest().frame("server.closing", { reason: "shutdown" });
    expect(rec.ends).toEqual([null]);
    expect(rec.modes.at(-1)).toBe("closed");
  });
});

describe("run event client: polling fallback", () => {
  it("polls when the browser offers no EventSource", async () => {
    const fetchImpl = vi.fn(async () => page([event(1, "node_started", { node_id: "dense" })]));
    const scheduler = manualScheduler();
    const rec = recorder();
    followRunEvents({ runId: "r1", eventSource: null, fetchImpl, schedule: scheduler.schedule, ...rec });
    await vi.waitFor(() => expect(rec.events).toHaveLength(1));
    expect(rec.modes[0]).toBe("polling");
    expect(fetchImpl).toHaveBeenCalledWith("/v1/runs/r1/events?after_sequence=0&limit=500", expect.anything());
  });

  it("falls back to polling after the stream is refused, resuming after the last sequence", async () => {
    const factory = eventSourceFactory();
    const fetchImpl = vi.fn(async () => page([event(3, "node_completed", { node_id: "dense" })], true, "succeeded"));
    const rec = recorder();
    followRunEvents({ runId: "r1", eventSource: factory, fetchImpl, schedule: manualScheduler().schedule, ...rec });
    const source = FakeEventSource.latest();
    source.open();
    source.send(event(1, "node_started", { node_id: "dense" }));
    source.send(event(2, "node_progress", { node_id: "dense" }));
    source.fail(true);
    expect(source.readyState).toBe(2);
    await vi.waitFor(() => expect(rec.ends).toEqual(["succeeded"]));
    expect(fetchImpl).toHaveBeenNthCalledWith(1, "/v1/runs/r1/events?after_sequence=2&limit=500", expect.anything());
    expect(rec.events.map((e) => e.sequence)).toEqual([1, 2, 3]);
    expect(rec.modes).toEqual(expect.arrayContaining(["streaming", "polling", "ended"]));
  });

  it("falls back after repeated reconnect failures with no frame", async () => {
    const factory = eventSourceFactory();
    const fetchImpl = vi.fn(async () => page([], false));
    const rec = recorder();
    followRunEvents({ runId: "r1", eventSource: factory, fetchImpl, schedule: manualScheduler().schedule, maxStreamErrors: 3, ...rec });
    const source = FakeEventSource.latest();
    source.fail(false);
    source.fail(false);
    expect(fetchImpl).not.toHaveBeenCalled();
    source.fail(false);
    await vi.waitFor(() => expect(fetchImpl).toHaveBeenCalled());
    expect(source.readyState).toBe(2);
  });

  it("deduplicates repeated polling pages and stops when the run is complete", async () => {
    const pages = [
      page([event(1, "node_started"), event(2, "node_completed")]),
      page([event(2, "node_completed"), event(3, "run.status", { summary: { status: "failed" } })], true, "failed"),
    ];
    const fetchImpl = vi.fn(async () => pages.shift() ?? page([], true, "failed"));
    const scheduler = manualScheduler();
    const rec = recorder();
    followRunEvents({ runId: "r1", eventSource: null, fetchImpl, schedule: scheduler.schedule, pollIntervalMs: 900, ...rec });
    await vi.waitFor(() => expect(rec.events).toHaveLength(2));
    expect(scheduler.pendingDelays()).toEqual([900]);
    scheduler.flush();
    await vi.waitFor(() => expect(rec.ends).toEqual(["failed"]));
    expect(rec.events.map((e) => e.sequence)).toEqual([1, 2, 3]);
    expect(scheduler.pendingDelays()).toEqual([]);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it("stops polling on an unknown run and reports the error", async () => {
    const fetchImpl = vi.fn(async () => json({ status: "error", message: "Unknown run." }, 404));
    const scheduler = manualScheduler();
    const errors: string[] = [];
    const rec = recorder();
    followRunEvents({ runId: "r1", eventSource: null, fetchImpl, schedule: scheduler.schedule, onError: (m) => errors.push(m), ...rec });
    await vi.waitFor(() => expect(errors).toEqual(["Unknown run."]));
    expect(scheduler.pendingDelays()).toEqual([]);
    expect(rec.modes.at(-1)).toBe("closed");
  });

  it("retries polling after a network error", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("offline");
    });
    const scheduler = manualScheduler();
    followRunEvents({ runId: "r1", eventSource: null, fetchImpl, schedule: scheduler.schedule, ...recorder() });
    await vi.waitFor(() => expect(scheduler.pendingDelays()).toHaveLength(1));
  });

  it("close() stops both the stream and further polls", async () => {
    const factory = eventSourceFactory();
    const handle = followRunEvents({ runId: "r1", eventSource: factory, ...recorder() });
    handle.close();
    expect(FakeEventSource.latest().readyState).toBe(2);
  });
});

describe("run event client: authoritative refresh on reconnect", () => {
  function server(status: { current: string; last: number }) {
    return vi.fn(async (path: string) =>
      path === "/v1/runs/r1"
        ? json({ status: "ok", run: { run_id: "r1", status: status.current, last_sequence: status.last } })
        : page([], false, status.current),
    );
  }
  const recordReads = (fetchImpl: ReturnType<typeof server>) => fetchImpl.mock.calls.filter(([path]) => path === "/v1/runs/r1").length;

  it("re-reads the run record each time the dropped stream reopens", async () => {
    const factory = eventSourceFactory();
    const status = { current: "running", last: 2 };
    const fetchImpl = server(status);
    const refreshed: string[] = [];
    followRunEvents({ runId: "r1", eventSource: factory, fetchImpl, onRefresh: (run) => refreshed.push(run.status), ...recorder() });
    const source = FakeEventSource.latest();
    source.open();
    source.send(event(1, "node_started", { node_id: "dense" }));
    // The first open is not a reconnect: the caller read the record before it followed events.
    expect(recordReads(fetchImpl)).toBe(0);
    source.fail(false);
    source.open();
    await vi.waitFor(() => expect(refreshed).toEqual(["running"]));
    status.current = "cancelling";
    source.fail(false);
    source.fail(false);
    source.open();
    await vi.waitFor(() => expect(refreshed).toEqual(["running", "cancelling"]));
    expect(recordReads(fetchImpl)).toBe(2);
  });

  it("re-reads the run record when it switches to polling", async () => {
    const factory = eventSourceFactory();
    const fetchImpl = server({ current: "succeeded", last: 9 });
    const refreshed: string[] = [];
    followRunEvents({ runId: "r1", eventSource: factory, fetchImpl, schedule: manualScheduler().schedule, onRefresh: (run) => refreshed.push(run.status), ...recorder() });
    const source = FakeEventSource.latest();
    source.open();
    source.fail(true);
    await vi.waitFor(() => expect(refreshed).toEqual(["succeeded"]));
    expect(recordReads(fetchImpl)).toBe(1);
  });

  it("re-reads the run record when polling recovers after a failure", async () => {
    let offline = true;
    const ok = server({ current: "running", last: 0 });
    const fetchImpl = vi.fn(async (path: string) => {
      if (offline) throw new TypeError("offline");
      return ok(path);
    });
    const scheduler = manualScheduler();
    const refreshed: string[] = [];
    followRunEvents({ runId: "r1", eventSource: null, fetchImpl, schedule: scheduler.schedule, onRefresh: (run) => refreshed.push(run.status), ...recorder() });
    await vi.waitFor(() => expect(scheduler.pendingDelays()).toHaveLength(1));
    expect(refreshed).toEqual([]);
    offline = false;
    scheduler.flush();
    await vi.waitFor(() => expect(refreshed).toEqual(["running"]));
  });

  it("reports a failed re-read and keeps following events", async () => {
    const factory = eventSourceFactory();
    const fetchImpl = vi.fn(async () => json({ status: "error", message: "Run store busy." }, 503));
    const errors: string[] = [];
    const rec = recorder();
    followRunEvents({ runId: "r1", eventSource: factory, fetchImpl, onRefresh: () => undefined, onError: (m) => errors.push(m), ...rec });
    const source = FakeEventSource.latest();
    source.open();
    source.fail(false);
    source.open();
    await vi.waitFor(() => expect(errors).toEqual(["Run store busy."]));
    source.send(event(1, "node_started", { node_id: "dense" }));
    expect(rec.events).toHaveLength(1);
    expect(rec.modes.at(-1)).toBe("streaming");
  });
});
