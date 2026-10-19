import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient } from "./client";
import {
  getPipeline,
  getRevision,
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
    const api = createApiClient(fetchImpl);
    const operations = await listOperations(api);
    expect(operations).toEqual([{ operation_id: "retrieve.dense" }]);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/pipeline-operations");
  });

  it("saves a layout with PUT and never posts a revision", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", pipeline: { pipeline_id: "p1" } }));
    const api = createApiClient(fetchImpl);
    await saveLayout(api, "p1", { title: "T", positions: {} });
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/pipelines/p1/layout");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ layout: { title: "T", positions: {} } });
  });

  it("reads one revision of a pipeline", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", revision: { revision_id: "p1-r1", revision_number: 1 } }));
    const api = createApiClient(fetchImpl);
    expect((await getRevision(api, "p1", "p1-r1")).revision_number).toBe(1);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/pipelines/p1/revisions/p1-r1");
    const refused = await getRevision(api, "p1", "../x").catch((e: unknown) => e);
    expect((refused as ApiError).kind).toBe("invalid-path");
  });

  it("saves a revision with the execution document only", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", revision: { revision_id: "r1" }, created: true }, 201));
    const api = createApiClient(fetchImpl);
    const saved = await saveRevision(api, "p1", DOC);
    expect(saved).toEqual({ revision: { revision_id: "r1" }, created: true, affected_collections: [] });
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/pipelines/p1/revisions");
    expect(JSON.parse(String(init?.body))).toEqual({ document: DOC });
  });

  it("returns the collections that a revision save affects", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", revision: { revision_id: "r2" }, created: true, affected_collections: ["kb-a", "kb-b"] }, 201));
    const api = createApiClient(fetchImpl);
    const saved = await saveRevision(api, "p1", DOC);
    expect(saved.affected_collections).toEqual(["kb-a", "kb-b"]);
  });

  it("reports structured validation issues from a 422 envelope", async () => {
    const issues = [{ code: "cycle", message: "The connections form a loop.", node_id: "fuse", port: null }];
    const fetchImpl = fetchReturning(
      json({ status: "error", message: "Invalid graph.", error_type: "validation", issues }, 422),
    );
    const api = createApiClient(fetchImpl);
    const failure = await validatePipeline(api, DOC, { inputs: { query: "q" } }).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(PipelineIssuesError);
    expect((failure as PipelineIssuesError).issues).toEqual(issues);
    expect((failure as PipelineIssuesError).status).toBe(422);
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/pipelines/validate");
    expect(JSON.parse(String(init?.body))).toEqual({ document: DOC, inputs: { query: "q" } });
  });

  it("keeps the effective controls that a refused draft check carries", async () => {
    const nodes = [{ node_id: "dense", controls: [{ lever: "retrieval.top_k", value: 10, source: "profile", detail: "profile" }] }];
    const issues = [{ code: "unknown_node", message: "No such node." }];
    const refused = createApiClient(fetchReturning(json({ status: "error", message: "Invalid graph.", issues, nodes }, 422)));
    const failure = await validatePipeline(refused, DOC, {}).catch((e: unknown) => e);
    expect((failure as PipelineIssuesError).nodes).toEqual(nodes);
    const bare = createApiClient(fetchReturning(json({ status: "error", message: "Invalid graph.", issues }, 422)));
    const noNodes = await validatePipeline(bare, DOC, {}).catch((e: unknown) => e);
    expect((noNodes as PipelineIssuesError).nodes).toBeUndefined();
  });

  it("omits inputs from a draft validation", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", valid: true, admitted: false, order: ["dense"] }));
    const api = createApiClient(fetchImpl);
    const report = await validatePipeline(api, DOC, {});
    expect(report.valid).toBe(true);
    expect(JSON.parse(String(fetchImpl.mock.calls[0]?.[1]?.body))).toEqual({ document: DOC });
  });

  it("submits a run by revision id", async () => {
    const submit = fetchReturning(json({ status: "ok", run: { run_id: "run1", status: "queued" } }, 202));
    const submitApi = createApiClient(submit);
    const run = await submitRun(submitApi, "r1", { query: "q" });
    expect(run.run_id).toBe("run1");
    expect(JSON.parse(String(submit.mock.calls[0]?.[1]?.body))).toEqual({ revision_id: "r1", inputs: { query: "q" } });
  });

  it("rejects an HTML answer to a POST without parsing it", async () => {
    const fetchImpl = fetchReturning(new Response("<!doctype html>", { status: 200, headers: { "content-type": "text/html" } }));
    const api = createApiClient(fetchImpl);
    const failure = await saveRevision(api, "p1", DOC).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).kind).toBe("not-json");
  });

  it("reports an ordinary error envelope as an http error", async () => {
    const fetchImpl = fetchReturning(json({ status: "error", message: "Unknown pipeline." }, 404));
    const api = createApiClient(fetchImpl);
    const failure = await getPipeline(api, "p9").catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).not.toBeInstanceOf(PipelineIssuesError);
    expect((failure as ApiError).message).toBe("Unknown pipeline.");
  });

  it("refuses identifiers that would change the path, before fetch", async () => {
    const fetchImpl = fetchReturning(json({}));
    const api = createApiClient(fetchImpl);
    for (const id of ["../health", "a/b", "", "p1?x=1"]) {
      const failure = await saveLayout(api, id, {}).catch((e: unknown) => e);
      expect((failure as ApiError).kind).toBe("invalid-path");
    }
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
