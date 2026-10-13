import { vi } from "vitest";
import type { GraphDocument, PipelineRecord, RevisionRecord } from "../../api/pipelines";
import { CATALOGUE } from "./catalogueFixture";

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

export interface FakeServerOptions {
  pipelines?: PipelineRecord[];
  revisions?: RevisionRecord[];
  validate?: (body: { document: GraphDocument; inputs?: Record<string, unknown> }) => Response;
  /** Answers `GET /v1/pipeline-templates`; omitted means the route is missing (404). */
  templates?: unknown[];
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

/** In-memory stand-in for the `/v1` graph and run routes. Records every request. */
export function fakeServer(options: FakeServerOptions = {}) {
  const calls: Call[] = [];
  const pipelines = new Map((options.pipelines ?? []).map((p) => [p.pipeline_id, { ...p }]));
  const revisions = new Map((options.revisions ?? []).map((r) => [r.revision_id, r]));
  let runStatus = "queued";

  function pipelineRoute(method: string, id: string, rest: string, body: Record<string, unknown>): Response {
    const pipeline = pipelines.get(id);
    if (pipeline === undefined) return json({ status: "error", message: "Unknown pipeline." }, 404);
    if (method === "GET" && rest === "") {
      const current = pipeline.current_revision_id ? revisions.get(pipeline.current_revision_id) : null;
      return json({ status: "ok", pipeline, current_revision: current ?? null });
    }
    if (method === "PUT" && rest === "/layout") {
      pipeline.layout = body.layout as PipelineRecord["layout"];
      return json({ status: "ok", pipeline });
    }
    if (method === "POST" && rest === "/revisions") {
      const number = [...revisions.values()].filter((r) => r.pipeline_id === id).length + 1;
      const revision: RevisionRecord = {
        revision_id: `${id}-r${number}`,
        pipeline_id: id,
        revision_number: number,
        content_hash: `hash${number}`,
        schema_version: 1,
        document: body.document as GraphDocument,
        created_at: "2026-10-13T12:00:00Z",
      };
      revisions.set(revision.revision_id, revision);
      pipeline.current_revision_id = revision.revision_id;
      return json({ status: "ok", revision, created: true }, 201);
    }
    return json({ status: "error", message: "Not found." }, 404);
  }

  function route(method: string, path: string, body: Record<string, unknown>): Response {
    if (path === "/v1/pipeline-operations") return json({ status: "ok", operations: CATALOGUE });
    if (path === "/v1/pipeline-templates" && options.templates) return json({ status: "ok", templates: options.templates });
    if (path === "/v1/pipelines" && method === "GET") return json({ status: "ok", pipelines: [...pipelines.values()] });
    if (path === "/v1/pipelines" && method === "POST") {
      const pipeline: PipelineRecord = {
        pipeline_id: "pnew",
        title: String(body.title),
        current_revision_id: null,
        layout: (body.layout ?? {}) as PipelineRecord["layout"],
        created_at: "2026-10-13T12:00:00Z",
        updated_at: "2026-10-13T12:00:00Z",
      };
      pipelines.set(pipeline.pipeline_id, pipeline);
      return json({ status: "ok", pipeline }, 201);
    }
    if (path === "/v1/pipelines/validate") {
      const custom = options.validate?.(body as { document: GraphDocument; inputs?: Record<string, unknown> });
      if (custom !== undefined) return custom;
      const nodes = (body.document as GraphDocument).nodes.map((n) => n.id);
      return json({ status: "ok", valid: true, admitted: body.inputs !== undefined, order: nodes, nodes: [] });
    }
    if (path === "/v1/runs" && method === "POST") {
      runStatus = "queued";
      return json({ status: "ok", run: { run_id: "run1", status: runStatus, revision_id: body.revision_id } }, 202);
    }
    if (path === "/v1/runs/run1/cancel") {
      runStatus = "cancelling";
      return json({ status: "ok", run: { run_id: "run1", status: runStatus } });
    }
    if (path === "/v1/runs/run1") return json({ status: "ok", run: { run_id: "run1", status: runStatus } });
    const match = /^\/v1\/pipelines\/([^/]+)(.*)$/.exec(path);
    if (match) return pipelineRoute(method, match[1]!, match[2]!, body);
    return json({ status: "error", message: "Not found." }, 404);
  }

  const fetchImpl = vi.fn(async (path: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
    calls.push({ method, path, body: init?.body ? body : undefined });
    return route(method, path, body);
  });

  function last(method: string, path: string): Call | undefined {
    return [...calls].reverse().find((call) => call.method === method && call.path === path);
  }

  return { fetchImpl, calls, last };
}
