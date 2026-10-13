/**
 * Typed client for the run routes of the local `/v1` API.
 *
 * Shapes follow `src/omrg/transports/api/routes_runs.py` and
 * `routes_inspect.py`. GET requests reuse `getJson`. The two POST routes
 * (cancel, retry) apply the same JSON and error-envelope checks.
 */
import { ApiError, getJson, type RequestOptions } from "./client";

export const RUN_STATUSES = ["queued", "running", "cancelling", "succeeded", "failed", "cancelled", "interrupted"] as const;
export const ACTIVE_RUN_STATUSES: ReadonlySet<string> = new Set(["queued", "running", "cancelling"]);
export const RETRYABLE_RUN_STATUSES: ReadonlySet<string> = new Set(["failed", "cancelled", "interrupted"]);

/** One admitted run. `settings`, `resources` and `failure` arrive redacted by the server. */
export interface RunDetailRecord {
  run_id: string;
  pipeline_id: string;
  revision_id: string;
  graph_hash: string;
  status: string;
  origin: string;
  source_run_id: string | null;
  settings: Record<string, unknown>;
  resources: Record<string, unknown>;
  inputs: Record<string, unknown>;
  failure: Record<string, unknown> | null;
  result_ref: string | null;
  last_sequence: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface RunEventRecord {
  run_id: string;
  sequence: number;
  kind: string;
  node_id: string | null;
  unit_id: string | null;
  summary: Record<string, unknown>;
  created_at: string;
}

export interface RunEventsPage {
  run_id: string;
  run_status: string;
  events: RunEventRecord[];
  last_sequence: number;
  complete: boolean;
}

export interface NodeOutcomeRecord {
  node_id: string;
  status: string;
  error: string | null;
  fallback: string | null;
  effects: string[];
  duration_s: number | null;
  unit_id: string | null;
}

/** The stored, redacted `PipelineResult`. `wall_time_s` is the measured end-to-end time. */
export interface RunResultRecord {
  run_id?: string;
  status?: string;
  graph_identity?: string;
  outputs?: Record<string, unknown>;
  nodes?: NodeOutcomeRecord[];
  failed_node?: string | null;
  completed_effects?: string[];
  wall_time_s?: number | null;
  error?: string | null;
}

export interface ChunkRecord {
  chunk_id: string | null;
  source_id: string | null;
  source: string | null;
  source_chunk_index: number | null;
  source_chunk_count: number | null;
  page_label: string | null;
  text: string;
}

export interface ChunkView {
  collection: string;
  text_format: string;
  chunk: ChunkRecord;
}

export const MAX_EVENT_PAGE = 500;
const RUN_ID = /^[A-Za-z0-9_-]+$/;

function runPath(runId: string, rest = ""): string {
  if (!RUN_ID.test(runId)) throw new ApiError("invalid-path", `Refused an unsafe run identifier: ${runId}`, "/v1/runs");
  return `/v1/runs/${runId}${rest}`;
}

async function postJson<T>(path: string, options: RequestOptions): Promise<T> {
  const fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
  let response: Response;
  try {
    response = await fetchImpl(path, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      credentials: "same-origin",
      body: "{}",
      signal: options.signal,
    });
  } catch (error) {
    throw new ApiError("network", `Could not reach the local server: ${error instanceof Error ? error.message : String(error)}`, path);
  }
  const type = response.headers.get("content-type")?.split(";")[0]?.trim().toLowerCase() ?? "";
  if (type !== "application/json") {
    throw new ApiError("not-json", `Expected JSON from ${path} but received ${type || "no content type"}.`, path, response.status);
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError("invalid-json", `The response from ${path} is not valid JSON.`, path, response.status);
  }
  if (!response.ok) {
    const raw = (body as { message?: unknown } | null)?.message;
    const message = typeof raw === "string" && raw ? raw : `Request to ${path} failed with status ${response.status}.`;
    throw new ApiError("http", message, path, response.status);
  }
  return body as T;
}

export async function listRuns(
  filter: { statuses?: readonly string[]; limit?: number },
  options: RequestOptions = {},
): Promise<RunDetailRecord[]> {
  const query = new URLSearchParams();
  for (const status of filter.statuses ?? []) query.append("status", status);
  if (filter.limit !== undefined) query.set("limit", String(filter.limit));
  const search = query.toString();
  return (await getJson<{ runs: RunDetailRecord[] }>(`/v1/runs${search ? `?${search}` : ""}`, options)).runs;
}

export async function getRunRecord(runId: string, options: RequestOptions = {}): Promise<RunDetailRecord> {
  return (await getJson<{ run: RunDetailRecord }>(runPath(runId), options)).run;
}

/** Returns `null` when the run has no stored result yet (HTTP 404). */
export async function getRunResult(runId: string, options: RequestOptions = {}): Promise<RunResultRecord | null> {
  try {
    return (await getJson<{ result: RunResultRecord }>(runPath(runId, "/result"), options)).result;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function listRunEvents(runId: string, afterSequence: number, options: RequestOptions = {}): Promise<RunEventsPage> {
  return getJson<RunEventsPage>(runPath(runId, `/events?after_sequence=${afterSequence}&limit=${MAX_EVENT_PAGE}`), options);
}

export async function cancelRunRecord(runId: string, options: RequestOptions = {}): Promise<RunDetailRecord> {
  return (await postJson<{ run: RunDetailRecord }>(runPath(runId, "/cancel"), options)).run;
}

/** Explicit retry: the server creates a new run and leaves the source run unchanged. */
export async function retryRun(runId: string, options: RequestOptions = {}): Promise<RunDetailRecord> {
  return (await postJson<{ run: RunDetailRecord }>(runPath(runId, "/retry"), options)).run;
}

/** The protected stored-chunk route. Text comes back as plain text and must render as text. */
export async function getChunk(collection: string, chunkId: string, options: RequestOptions = {}): Promise<ChunkView> {
  const path = `/v1/collections/${encodeURIComponent(collection)}/chunks/${encodeURIComponent(chunkId)}?window=0`;
  return getJson<ChunkView>(path, options);
}

/** Server-sent events path. A fresh stream resumes with `after`; the browser's own reconnect sends `Last-Event-ID`. */
export function eventStreamPath(runId: string, afterSequence: number): string {
  return runPath(runId, `/events/stream${afterSequence > 0 ? `?after=${afterSequence}` : ""}`);
}
