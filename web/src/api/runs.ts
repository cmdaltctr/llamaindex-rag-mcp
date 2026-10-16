/**
 * Typed client for the run routes of the local `/v1` API.
 *
 * Shapes follow `src/omrg/transports/api/routes/runs.py` and
 * `inspection.py`. Every function takes the `ApiClient` first.
 */
import { ApiError, type ApiClient, type CallOptions } from "./client";

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
  /** Bounded, redacted node summary; older stored results have none. */
  summary?: Record<string, unknown> | null;
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

export const MAX_EVENT_PAGE = 500;
const RUN_ID = /^[A-Za-z0-9_-]+$/;
/** One artefact name: the server's own segment rule (`core/workspace/artefacts.py`), with no `..`. */
const ARTEFACT_NAME = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/;

function isArtefactName(name: string): boolean {
  return ARTEFACT_NAME.test(name) && !name.includes("..");
}

function runPath(runId: string, rest = ""): string {
  if (!RUN_ID.test(runId)) throw new ApiError("invalid-path", `Refused an unsafe run identifier: ${runId}`, "/v1/runs");
  return `/v1/runs/${runId}${rest}`;
}

export async function listRuns(
  api: ApiClient,
  filter: { statuses?: readonly string[]; limit?: number; pipelineId?: string },
  options: CallOptions = {},
): Promise<RunDetailRecord[]> {
  // `query` holds one value per key, and the server reads `status` as a repeated key.
  const query = new URLSearchParams();
  for (const status of filter.statuses ?? []) query.append("status", status);
  if (filter.limit !== undefined) query.set("limit", String(filter.limit));
  if (filter.pipelineId !== undefined) query.set("pipeline_id", filter.pipelineId);
  const search = query.toString();
  const path = `/v1/runs${search ? `?${search}` : ""}`;
  return (await api.request<{ runs: RunDetailRecord[] }>("GET", path, { signal: options.signal })).runs;
}

export async function getRunRecord(api: ApiClient, runId: string, options: CallOptions = {}): Promise<RunDetailRecord> {
  return (await api.request<{ run: RunDetailRecord }>("GET", runPath(runId), { signal: options.signal })).run;
}

/** Returns `null` when the run has no stored result yet (HTTP 404). */
export async function getRunResult(api: ApiClient, runId: string, options: CallOptions = {}): Promise<RunResultRecord | null> {
  try {
    return (await api.request<{ result: RunResultRecord }>("GET", runPath(runId, "/result"), { signal: options.signal })).result;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function listRunEvents(api: ApiClient, runId: string, afterSequence: number, options: CallOptions = {}): Promise<RunEventsPage> {
  return api.request<RunEventsPage>("GET", runPath(runId, "/events"), {
    query: { after_sequence: afterSequence, limit: MAX_EVENT_PAGE },
    signal: options.signal,
  });
}

export async function cancelRunRecord(api: ApiClient, runId: string, options: CallOptions = {}): Promise<RunDetailRecord> {
  return (await api.request<{ run: RunDetailRecord }>("POST", runPath(runId, "/cancel"), { body: {}, signal: options.signal })).run;
}

/** Explicit retry: the server creates a new run and leaves the source run unchanged. */
export async function retryRun(api: ApiClient, runId: string, options: CallOptions = {}): Promise<RunDetailRecord> {
  return (await api.request<{ run: RunDetailRecord }>("POST", runPath(runId, "/retry"), { body: {}, signal: options.signal })).run;
}

/**
 * The artefact name in an `artefact_ref` (`"<run_id>/<name>.json"`), or
 * `null` when the reference is malformed or names another run. Only the run
 * shown can be read, so a reference to any other run offers no action.
 */
export function artefactName(ref: unknown, runId: string): string | null {
  if (typeof ref !== "string") return null;
  const parts = ref.split("/");
  if (parts.length !== 2 || parts[0] !== runId || !parts[1]!.endsWith(".json")) return null;
  const name = parts[1]!.slice(0, -".json".length);
  return isArtefactName(name) ? name : null;
}

/** The full, redacted value of one artefact of a run, such as a node summary the server cut. */
export async function getRunArtefact(api: ApiClient, runId: string, name: string, options: CallOptions = {}): Promise<unknown> {
  if (!isArtefactName(name)) throw new ApiError("invalid-path", `Refused an unsafe artefact name: ${name}`, "/v1/runs");
  return (await api.request<{ value: unknown }>("GET", runPath(runId, `/artefacts/${name}`), { signal: options.signal })).value;
}

/** Server-sent events path. A fresh stream resumes with `after`; the browser's own reconnect sends `Last-Event-ID`. */
export function eventStreamPath(runId: string, afterSequence: number): string {
  return runPath(runId, `/events/stream${afterSequence > 0 ? `?after=${afterSequence}` : ""}`);
}
