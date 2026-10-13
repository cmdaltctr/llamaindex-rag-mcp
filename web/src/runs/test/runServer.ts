import { vi } from "vitest";
import type { RunDetailRecord, RunEventRecord, RunResultRecord } from "../../api/runs";
import { event, json } from "./fakes";

export const SECRET = "sk-live-abcdef1234567890";

const RERANK_ROWS = [
  { chunk_id: "c-long", source: "guide.md", collection: "docs", text: "x".repeat(5000), score: 0.91234, score_kind: "reranker_sigmoid_v1", fused_rank: 3 },
  { chunk_id: "c-html", source: "notes.md", collection: "docs", text: "<b>bold</b> text", score: 0.5, score_kind: "reranker_sigmoid_v1" },
];

export const FAILED_RUN: RunDetailRecord = {
  run_id: "r1",
  pipeline_id: "p1",
  revision_id: "p1-r3",
  graph_hash: "sha256:abc123",
  status: "failed",
  origin: "submit",
  source_run_id: null,
  settings: { docs: { profile: "documents", origin: "collection", settings: { api_key: "[redacted]", headers: { Authorization: `Bearer ${SECRET}` }, top_k: 10 } } },
  resources: { graph_identity: "gid-1", schema_version: 1, operations: { dense: "retrieve.dense@1", rerank: "select.rerank@1" } },
  inputs: { query: "What is RRF?" },
  failure: { reason: "failed", failed_node: "answer", error: `upstream refused Bearer ${SECRET}`, completed_effects: ["source:a.md"] },
  result_ref: "r1/result.json",
  last_sequence: 6,
  created_at: "2026-10-13T12:00:00Z",
  started_at: "2026-10-13T12:00:01Z",
  finished_at: "2026-10-13T12:00:05Z",
};

export const ACTIVE_RUN: RunDetailRecord = { ...FAILED_RUN, run_id: "r2", status: "running", failure: null, result_ref: null, finished_at: null };

export const FAILED_RESULT: RunResultRecord = {
  status: "failed",
  graph_identity: "gid-1",
  failed_node: "answer",
  completed_effects: ["source:a.md"],
  wall_time_s: 2.5,
  error: "Node 'answer' failed",
  nodes: [
    { node_id: "dense", status: "succeeded", error: null, fallback: null, effects: [], duration_s: 1.25, unit_id: null },
    { node_id: "rerank", status: "succeeded", error: null, fallback: "reranker model unavailable", effects: [], duration_s: 1.5, unit_id: null },
    { node_id: "answer", status: "failed", error: "TimeoutError: model", fallback: null, effects: [], duration_s: 0.4, unit_id: null },
  ],
  outputs: {
    reranked: RERANK_ROWS,
    fused: Array.from({ length: 130 }, (_, i) => ({ chunk_id: `f${i}`, source: "a.md", text: `row ${i}`, score: 0.03 - i / 10000, score_kind: "rrf_v1" })),
    sparse: [{ chunk_id: "s1", source: "a.md", text: "sparse row", score: 2, score_kind: "sparse_rank_v1" }],
    answer: { answer: "RRF fuses ranks.", citations: [{ ordinal: 1, chunk_id: "c-html", source: "notes.md", score: 0.5, score_kind: "reranker_sigmoid_v1" }] },
  },
};

export const FAILED_EVENTS: RunEventRecord[] = [
  event(1, "run.status", { summary: { status: "running" } }),
  event(2, "node_started", { node_id: "dense" }),
  event(3, "node_completed", { node_id: "dense" }),
  event(4, "node_started", { node_id: "answer" }),
  event(5, "node_failed", { node_id: "answer", summary: { message: "TimeoutError: model" } }),
  event(6, "run.status", { summary: { status: "failed", wall_time_s: 2.5 } }),
];

interface RunServerOptions {
  runs?: RunDetailRecord[];
  results?: Record<string, RunResultRecord>;
  events?: Record<string, RunEventRecord[]>;
}

/** In-memory stand-in for the run and chunk routes. Records every request. */
export function runServer(options: RunServerOptions = {}) {
  const runs = new Map((options.runs ?? [FAILED_RUN, ACTIVE_RUN]).map((run) => [run.run_id, { ...run }]));
  const results = options.results ?? { r1: FAILED_RESULT };
  const events = options.events ?? { r1: FAILED_EVENTS };
  const calls: { method: string; path: string }[] = [];

  function route(method: string, url: URL): Response {
    const path = url.pathname;
    if (path === "/v1/runs") {
      const statuses = url.searchParams.getAll("status");
      const listed = [...runs.values()].filter((run) => statuses.length === 0 || statuses.includes(run.status));
      return json({ status: "ok", runs: listed });
    }
    const chunk = /^\/v1\/collections\/([^/]+)\/chunks\/([^/]+)$/.exec(path);
    if (chunk) {
      const text = `Full text of ${decodeURIComponent(chunk[2]!)} <script>alert(1)</script>`;
      return json({ status: "ok", collection: decodeURIComponent(chunk[1]!), text_format: "plain", chunk: { chunk_id: chunk[2], source: "notes.md", source_chunk_index: 2, text } });
    }
    const match = /^\/v1\/runs\/([^/]+)(\/[a-z]+)?$/.exec(path);
    const run = match ? runs.get(match[1]!) : undefined;
    if (!match || !run) return json({ status: "error", message: "Unknown run." }, 404);
    const rest = match[2] ?? "";
    if (method === "GET" && rest === "") return json({ status: "ok", run });
    if (rest === "/result") {
      const result = results[run.run_id];
      return result ? json({ status: "ok", run_id: run.run_id, result }) : json({ status: "error", message: "This run has no stored result." }, 404);
    }
    if (rest === "/events") {
      const after = Number(url.searchParams.get("after_sequence") ?? 0);
      const list = (events[run.run_id] ?? []).filter((e) => e.sequence > after);
      const last = list.at(-1)?.sequence ?? after;
      const done = !["queued", "running", "cancelling"].includes(run.status);
      return json({ status: "ok", run_id: run.run_id, run_status: run.status, events: list, last_sequence: last, complete: done });
    }
    if (method === "POST" && rest === "/cancel") {
      run.status = "cancelling";
      return json({ status: "ok", run });
    }
    if (method === "POST" && rest === "/retry") {
      const retry = { ...run, run_id: "r9", status: "queued", origin: "retry", source_run_id: run.run_id, failure: null, result_ref: null };
      runs.set(retry.run_id, retry);
      return json({ status: "ok", run: retry }, 202);
    }
    return json({ status: "error", message: "Not found." }, 404);
  }

  const fetchImpl = vi.fn(async (path: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ method, path });
    return route(method, new URL(path, "http://omrg.test"));
  });

  return { fetchImpl, calls, runs };
}
