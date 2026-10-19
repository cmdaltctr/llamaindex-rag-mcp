import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient } from "./client";
import { artefactName, cancelRunRecord, eventStreamPath, getRunArtefact, getRunRecord, getRunResult, listRunEvents, listRuns, retryRun } from "./runs";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function fetchReturning(response: Response) {
  return vi.fn(async (input: string, init?: RequestInit) => {
    void input;
    void init;
    return response;
  });
}

describe("run API client", () => {
  it("lists runs with repeated status filters", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", runs: [{ run_id: "r1", status: "failed" }] }));
    const api = createApiClient(fetchImpl);
    const runs = await listRuns(api, { statuses: ["failed", "cancelled"], limit: 50 });
    expect(runs).toEqual([{ run_id: "r1", status: "failed" }]);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/runs?status=failed&status=cancelled&limit=50");
  });

  it("filters runs by pipeline", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", runs: [] }));
    await listRuns(createApiClient(fetchImpl), { pipelineId: "pl_1", limit: 1 });
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/runs?limit=1&pipeline_id=pl_1");
  });

  it("lists every run when no filter is given", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", runs: [] }));
    const api = createApiClient(fetchImpl);
    await listRuns(api, {});
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/runs");
  });

  it("reads one run record", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", run: { run_id: "r1", status: "running" } }));
    const api = createApiClient(fetchImpl);
    expect((await getRunRecord(api, "r1")).status).toBe("running");
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/runs/r1");
  });

  it("returns null when a run has no stored result", async () => {
    const fetchImpl = fetchReturning(json({ status: "error", message: "This run has no stored result." }, 404));
    const api = createApiClient(fetchImpl);
    expect(await getRunResult(api, "r1")).toBeNull();
  });

  it("returns the stored result", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", run_id: "r1", result: { status: "succeeded", nodes: [] } }));
    const api = createApiClient(fetchImpl);
    expect(await getRunResult(api, "r1")).toEqual({ status: "succeeded", nodes: [] });
  });

  it("polls events after a sequence", async () => {
    const page = { status: "ok", run_id: "r1", run_status: "running", events: [], last_sequence: 4, complete: false };
    const fetchImpl = fetchReturning(json(page));
    const api = createApiClient(fetchImpl);
    expect((await listRunEvents(api, "r1", 4)).last_sequence).toBe(4);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/runs/r1/events?after_sequence=4&limit=500");
  });

  it("cancels and retries with explicit POST requests", async () => {
    const fetchImpl = vi.fn(async (input: string, init?: RequestInit) => {
      void input;
      void init;
      return json({ status: "ok", run: { run_id: "r2", status: "queued", origin: "retry" } }, 202);
    });
    const api = createApiClient(fetchImpl);
    expect((await retryRun(api, "r1")).run_id).toBe("r2");
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/runs/r1/retry");
    expect(fetchImpl.mock.calls[0]?.[1]?.method).toBe("POST");
    await cancelRunRecord(api, "r1");
    expect(fetchImpl.mock.calls[1]?.[0]).toBe("/v1/runs/r1/cancel");
  });

  it("raises the error envelope message for a refused retry", async () => {
    const fetchImpl = fetchReturning(json({ status: "error", message: "Only failed runs can be retried." }, 409));
    const api = createApiClient(fetchImpl);
    await expect(retryRun(api, "r1")).rejects.toMatchObject({ status: 409, message: "Only failed runs can be retried." });
  });

  it("refuses an unsafe run identifier before any request", async () => {
    const fetchImpl = fetchReturning(json({}));
    const api = createApiClient(fetchImpl);
    await expect(getRunRecord(api, "../pipelines")).rejects.toBeInstanceOf(ApiError);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("builds the stream path with the resume sequence", () => {
    expect(eventStreamPath("r1", 0)).toBe("/v1/runs/r1/events/stream");
    expect(eventStreamPath("r1", 7)).toBe("/v1/runs/r1/events/stream?after=7");
  });
});

describe("run artefacts", () => {
  it("reads one artefact of a run by name and returns its value", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", run_id: "r1", name: "event-0a1b", value: { message: "m", data: { rows: [1] } } }));
    const api = createApiClient(fetchImpl);
    expect(await getRunArtefact(api, "r1", "event-0a1b")).toEqual({ message: "m", data: { rows: [1] } });
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/runs/r1/artefacts/event-0a1b");
  });

  it("refuses a name that is not one safe path segment before any request", async () => {
    const fetchImpl = fetchReturning(json({}));
    const api = createApiClient(fetchImpl);
    for (const name of ["..", ".", "a/b", "a\\b", "", ".hidden", "a..b", "x y", "%2e%2e"]) {
      await expect(getRunArtefact(api, "r1", name)).rejects.toBeInstanceOf(ApiError);
    }
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("raises the 404 of an unknown artefact", async () => {
    const fetchImpl = fetchReturning(json({ status: "error", message: "This run has no such output." }, 404));
    await expect(getRunArtefact(createApiClient(fetchImpl), "r1", "status-failed")).rejects.toMatchObject({ status: 404 });
  });

  it("derives the name from an artefact_ref only when its run part is the run shown", () => {
    expect(artefactName("r1/event-0a1b.json", "r1")).toBe("event-0a1b");
    expect(artefactName("r1/status-failed.json", "r1")).toBe("status-failed");
    expect(artefactName("r2/event-0a1b.json", "r1")).toBeNull();
    expect(artefactName("r1/event-0a1b", "r1")).toBeNull();
    expect(artefactName("r1/../r2/x.json", "r1")).toBeNull();
    expect(artefactName("r1/..json", "r1")).toBeNull();
    expect(artefactName("r1/a/b.json", "r1")).toBeNull();
    expect(artefactName("event.json", "r1")).toBeNull();
    expect(artefactName(42, "r1")).toBeNull();
    expect(artefactName(undefined, "r1")).toBeNull();
  });
});
