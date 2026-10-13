import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./client";
import { cancelRunRecord, eventStreamPath, getChunk, getRunRecord, getRunResult, listRunEvents, listRuns, retryRun } from "./runs";

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
    const runs = await listRuns({ statuses: ["failed", "cancelled"], limit: 50 }, { fetchImpl });
    expect(runs).toEqual([{ run_id: "r1", status: "failed" }]);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/runs?status=failed&status=cancelled&limit=50");
  });

  it("lists every run when no filter is given", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", runs: [] }));
    await listRuns({}, { fetchImpl });
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/runs");
  });

  it("reads one run record", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", run: { run_id: "r1", status: "running" } }));
    expect((await getRunRecord("r1", { fetchImpl })).status).toBe("running");
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/runs/r1");
  });

  it("returns null when a run has no stored result", async () => {
    const fetchImpl = fetchReturning(json({ status: "error", message: "This run has no stored result." }, 404));
    expect(await getRunResult("r1", { fetchImpl })).toBeNull();
  });

  it("returns the stored result", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", run_id: "r1", result: { status: "succeeded", nodes: [] } }));
    expect(await getRunResult("r1", { fetchImpl })).toEqual({ status: "succeeded", nodes: [] });
  });

  it("polls events after a sequence", async () => {
    const page = { status: "ok", run_id: "r1", run_status: "running", events: [], last_sequence: 4, complete: false };
    const fetchImpl = fetchReturning(json(page));
    expect((await listRunEvents("r1", 4, { fetchImpl })).last_sequence).toBe(4);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/runs/r1/events?after_sequence=4&limit=500");
  });

  it("cancels and retries with explicit POST requests", async () => {
    const fetchImpl = vi.fn(async (input: string, init?: RequestInit) => {
      void input;
      void init;
      return json({ status: "ok", run: { run_id: "r2", status: "queued", origin: "retry" } }, 202);
    });
    expect((await retryRun("r1", { fetchImpl })).run_id).toBe("r2");
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/runs/r1/retry");
    expect(fetchImpl.mock.calls[0]?.[1]?.method).toBe("POST");
    await cancelRunRecord("r1", { fetchImpl });
    expect(fetchImpl.mock.calls[1]?.[0]).toBe("/v1/runs/r1/cancel");
  });

  it("raises the error envelope message for a refused retry", async () => {
    const fetchImpl = fetchReturning(json({ status: "error", message: "Only failed runs can be retried." }, 409));
    await expect(retryRun("r1", { fetchImpl })).rejects.toMatchObject({ status: 409, message: "Only failed runs can be retried." });
  });

  it("encodes chunk and collection identifiers in the protected chunk route", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", collection: "docs a", text_format: "plain", chunk: { text: "x" } }));
    await getChunk("docs a", "src:1/2", { fetchImpl });
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/collections/docs%20a/chunks/src%3A1%2F2?window=0");
  });

  it("refuses an unsafe run identifier before any request", async () => {
    const fetchImpl = fetchReturning(json({}));
    await expect(getRunRecord("../pipelines", { fetchImpl })).rejects.toBeInstanceOf(ApiError);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("builds the stream path with the resume sequence", () => {
    expect(eventStreamPath("r1", 0)).toBe("/v1/runs/r1/events/stream");
    expect(eventStreamPath("r1", 7)).toBe("/v1/runs/r1/events/stream?after=7");
  });
});
