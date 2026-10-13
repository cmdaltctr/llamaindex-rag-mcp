import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./client";
import {
  cancelRun,
  createPipeline,
  getPipeline,
  listOperations,
  PipelineIssuesError,
  saveLayout,
  saveRevision,
  submitRun,
  validatePipeline,
} from "./pipelines";

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

const DOC = { schema_version: 1, nodes: [{ id: "dense", operation: "retrieve.dense" }] };

describe("pipeline API client", () => {
  it("reads the operation catalogue", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", operations: [{ operation_id: "retrieve.dense" }] }));
    const operations = await listOperations({ fetchImpl });
    expect(operations).toEqual([{ operation_id: "retrieve.dense" }]);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/pipeline-operations");
  });

  it("creates a pipeline with a POST body", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", pipeline: { pipeline_id: "p1" } }, 201));
    const pipeline = await createPipeline("Hybrid", { title: "Hybrid" }, { fetchImpl });
    expect(pipeline.pipeline_id).toBe("p1");
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/pipelines");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ title: "Hybrid", layout: { title: "Hybrid" } });
    expect(new Headers(init?.headers).get("content-type")).toBe("application/json");
  });

  it("saves a layout with PUT and never posts a revision", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", pipeline: { pipeline_id: "p1" } }));
    await saveLayout("p1", { title: "T", positions: {} }, { fetchImpl });
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/pipelines/p1/layout");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ layout: { title: "T", positions: {} } });
  });

  it("saves a revision with the execution document only", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", revision: { revision_id: "r1" }, created: true }, 201));
    const saved = await saveRevision("p1", DOC, { fetchImpl });
    expect(saved).toEqual({ revision: { revision_id: "r1" }, created: true });
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/pipelines/p1/revisions");
    expect(JSON.parse(String(init?.body))).toEqual({ document: DOC });
  });

  it("reports structured validation issues from a 422 envelope", async () => {
    const issues = [{ code: "cycle", message: "The connections form a loop.", node_id: "fuse", port: null }];
    const fetchImpl = fetchReturning(
      json({ status: "error", message: "Invalid graph.", error_type: "validation", issues }, 422),
    );
    const failure = await validatePipeline(DOC, { inputs: { query: "q" } }, { fetchImpl }).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(PipelineIssuesError);
    expect((failure as PipelineIssuesError).issues).toEqual(issues);
    expect((failure as PipelineIssuesError).status).toBe(422);
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/pipelines/validate");
    expect(JSON.parse(String(init?.body))).toEqual({ document: DOC, inputs: { query: "q" } });
  });

  it("omits inputs from a draft validation", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", valid: true, admitted: false, order: ["dense"] }));
    const report = await validatePipeline(DOC, {}, { fetchImpl });
    expect(report.valid).toBe(true);
    expect(JSON.parse(String(fetchImpl.mock.calls[0]?.[1]?.body))).toEqual({ document: DOC });
  });

  it("submits a run by revision id and cancels it", async () => {
    const submit = fetchReturning(json({ status: "ok", run: { run_id: "run1", status: "queued" } }, 202));
    const run = await submitRun("r1", { query: "q" }, { fetchImpl: submit });
    expect(run.run_id).toBe("run1");
    expect(JSON.parse(String(submit.mock.calls[0]?.[1]?.body))).toEqual({ revision_id: "r1", inputs: { query: "q" } });

    const cancel = fetchReturning(json({ status: "ok", run: { run_id: "run1", status: "cancelling" } }));
    expect((await cancelRun("run1", { fetchImpl: cancel })).status).toBe("cancelling");
    expect(cancel.mock.calls[0]?.[0]).toBe("/v1/runs/run1/cancel");
  });

  it("rejects an HTML answer to a POST without parsing it", async () => {
    const fetchImpl = fetchReturning(new Response("<!doctype html>", { status: 200, headers: { "content-type": "text/html" } }));
    const failure = await saveRevision("p1", DOC, { fetchImpl }).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).kind).toBe("not-json");
  });

  it("reports an ordinary error envelope as an http error", async () => {
    const fetchImpl = fetchReturning(json({ status: "error", message: "Unknown pipeline." }, 404));
    const failure = await getPipeline("p9", { fetchImpl }).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).not.toBeInstanceOf(PipelineIssuesError);
    expect((failure as ApiError).message).toBe("Unknown pipeline.");
  });

  it("refuses identifiers that would change the path, before fetch", async () => {
    const fetchImpl = fetchReturning(json({}));
    for (const id of ["../health", "a/b", "", "p1?x=1"]) {
      const failure = await saveLayout(id, {}, { fetchImpl }).catch((e: unknown) => e);
      expect((failure as ApiError).kind).toBe("invalid-path");
    }
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
