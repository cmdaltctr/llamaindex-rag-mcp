import type { RunDetailRecord, RunEventRecord, RunResultRecord } from "../../api/runs";
import { event } from "../../runs/test/fakes";

export const SECRET = "sk-live-abcdef1234567890"; // gitleaks:allow (fake key: the redaction tests need a key-shaped value)

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

/** A run admitted in an experiment context, in the shape the server stores it. */
export function experimentRun(runId: string, contextId: string | null, status = "succeeded"): RunDetailRecord {
  return {
    ...FAILED_RUN,
    run_id: runId,
    status,
    settings: {},
    // Same shape as the server: ExperimentEngine.resources() nests the identity under "backend".
    resources: contextId
      ? { experiment: { context_id: contextId, graph_identity: "h", backend: { context_id: contextId, index_identity: `idx-${contextId}`, store_kind: "lancedb" } } }
      : {},
    inputs: {},
    failure: null,
    result_ref: null,
    last_sequence: 3,
    created_at: "2026-10-13T12:30:00Z",
    started_at: null,
    finished_at: null,
  };
}
