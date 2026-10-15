import { vi } from "vitest";
import type { GraphDocument, PipelineRecord, RevisionRecord } from "../../api/pipelines";
import type { RunDetailRecord } from "../../api/runs";
import { CATALOGUE } from "./catalogueFixture";

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

export interface FakeServerOptions {
  pipelines?: PipelineRecord[];
  revisions?: RevisionRecord[];
  /** Runs that exist before the test starts, newest first. */
  runs?: Partial<RunDetailRecord>[];
  collections?: { name: string; document_count: number; chunk_count: number; profile: string | null; display_name: string | null; store: { name: string; label: string } }[];
  validate?: (body: { document: GraphDocument; inputs?: Record<string, unknown> }) => Response;
  /** Answers `GET /v1/pipeline-templates`; omitted means the route is missing (404). */
  templates?: unknown[];
  /** Routes that answer with an HTTP error, as `"METHOD /path": status`. Delete a key to let the route work again. */
  failures?: Record<string, number>;
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function runRecord(partial: Partial<RunDetailRecord>): RunDetailRecord {
  return {
    run_id: "run1",
    pipeline_id: "p1",
    revision_id: "p1-r1",
    graph_hash: "hash",
    status: "queued",
    origin: "user",
    source_run_id: null,
    settings: {},
    resources: {},
    inputs: {},
    failure: null,
    result_ref: null,
    last_sequence: 0,
    created_at: "2026-10-13T12:00:00Z",
    started_at: null,
    finished_at: null,
    ...partial,
  };
}

/** In-memory stand-in for the `/v1` graph and run routes. Records every request. */
export function fakeServer(options: FakeServerOptions = {}) {
  const calls: Call[] = [];
  const pipelines = new Map((options.pipelines ?? []).map((p) => [p.pipeline_id, { ...p }]));
  const revisions = new Map((options.revisions ?? []).map((r) => [r.revision_id, r]));
  const runs = (options.runs ?? []).map(runRecord);
  let created = 0;

  function pipelineRoute(method: string, id: string, rest: string, body: Record<string, unknown>): Response {
    const pipeline = pipelines.get(id);
    if (pipeline === undefined) return json({ status: "error", message: "Unknown pipeline." }, 404);
    if (method === "GET" && rest === "") {
      const current = pipeline.current_revision_id ? revisions.get(pipeline.current_revision_id) : null;
      return json({ status: "ok", pipeline, current_revision: current ?? null });
    }
    const one = /^\/revisions\/([^/]+)$/.exec(rest);
    if (method === "GET" && one) {
      const revision = revisions.get(one[1]!);
      return revision ? json({ status: "ok", revision }) : json({ status: "error", message: "Unknown revision." }, 404);
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

  function runRoute(method: string, url: URL, body: Record<string, unknown>): Response | null {
    if (url.pathname === "/v1/runs" && method === "GET") {
      const wanted = url.searchParams.get("pipeline_id");
      const limit = Number(url.searchParams.get("limit") ?? 100);
      return json({ status: "ok", runs: runs.filter((run) => wanted === null || run.pipeline_id === wanted).slice(0, limit) });
    }
    if (url.pathname === "/v1/runs" && method === "POST") {
      const revision = revisions.get(String(body.revision_id));
      const run = runRecord({
        run_id: `run${runs.length + 1}`,
        pipeline_id: revision?.pipeline_id ?? "unknown",
        revision_id: String(body.revision_id),
        inputs: (body.inputs ?? {}) as Record<string, unknown>,
      });
      runs.unshift(run);
      return json({ status: "ok", run }, 202);
    }
    const match = /^\/v1\/runs\/([^/]+)(\/cancel)?$/.exec(url.pathname);
    const run = match ? runs.find((candidate) => candidate.run_id === match[1]) : undefined;
    if (!match || run === undefined) return null;
    if (match[2]) {
      run.status = "cancelling";
      run.last_sequence += 1;
    }
    return json({ status: "ok", run });
  }

  function route(method: string, path: string, body: Record<string, unknown>): Response {
    const failure = options.failures?.[`${method} ${path}`];
    if (failure !== undefined) return json({ status: "error", message: "Boom: /srv/private/path" }, failure);
    const url = new URL(path, "http://localhost");
    if (path === "/v1/pipeline-operations") return json({ status: "ok", operations: CATALOGUE });
    if (path === "/v1/pipeline-templates" && options.templates) return json({ status: "ok", templates: options.templates });
    if (path === "/v1/collections") return json(options.collections ?? []);
    if (path === "/v1/pipelines" && method === "GET") return json({ status: "ok", pipelines: [...pipelines.values()] });
    if (path === "/v1/pipelines" && method === "POST") {
      created += 1;
      const pipeline: PipelineRecord = {
        pipeline_id: created === 1 ? "pnew" : `pnew${created}`,
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
    const asRun = runRoute(method, url, body);
    if (asRun !== null) return asRun;
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

  return { fetchImpl, calls, last, pipelines, revisions, runs, failures: options.failures ?? {} };
}
