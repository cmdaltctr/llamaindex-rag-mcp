/**
 * Typed client for the experiment context routes and bound credentials.
 *
 * Shapes follow `src/omrg/transports/api/routes_experiments.py` and
 * `POST /v1/credentials` in `routes.py`. Experiment refusals carry a stable
 * `code`; the user sees the server's `message`.
 */
import { joinRootPath } from "./documents";
import { ApiError, getJson, type RequestOptions } from "./client";

export interface ExperimentRecord {
  context_id: string;
  name: string;
  root: string;
  workspace: string;
  output_dir: string;
  store_backend: string;
  declared_factors: string[];
  actions: string[];
  approved_at: string;
  revoked_at: string | null;
  status: "active" | "revoked";
}

/** Backend and index identity of the context store. */
export interface BackendIdentity {
  context_id: string | null;
  store_kind: string;
  store_path: string;
  embedding_provider: string;
  embedding_model: string;
  index_identity: string;
}

export interface ExperimentEntry {
  experiment: ExperimentRecord;
  identity: BackendIdentity;
}

export interface ExperimentList {
  roots: string[];
  experiments: ExperimentEntry[];
  trust_notice: string;
}

export type ExperimentAction = "read" | "ingest";
export type BearerScope = "graph" | "read" | "run";

export interface ExperimentRequest {
  workspace: string;
  name: string;
  actions: ExperimentAction[];
}

export interface IssuedCredential {
  id: string;
  token: string;
  scopes: string[];
  label: string;
  experiment_context: string | null;
}

const SAFE_ID = /^[A-Za-z0-9_.-]+$/;

/** Returns `id` for use as one path segment. Refuses empty, dot and separator-bearing identifiers. */
export function safeId(id: string): string {
  if (!SAFE_ID.test(id) || id === "." || id === "..") {
    throw new ApiError("invalid-path", `Refused an unsafe identifier: ${JSON.stringify(id)}`, id);
  }
  return id;
}

function isJson(response: Response): boolean {
  const type = response.headers.get("content-type")?.split(";")[0]?.trim().toLowerCase() ?? "";
  return type === "application/json" || type.endsWith("+json");
}

/** Sends a JSON write to a `/v1/` path and returns the parsed success body. */
export async function sendJson<T>(method: "POST" | "DELETE", path: string, payload: unknown, options: RequestOptions): Promise<T> {
  const fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
  let response: Response;
  try {
    response = await fetchImpl(path, {
      method,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      credentials: "same-origin",
      body: payload === undefined ? undefined : JSON.stringify(payload),
      signal: options.signal,
    });
  } catch (error) {
    throw new ApiError("network", `Could not reach the local server: ${error instanceof Error ? error.message : String(error)}`, path);
  }
  if (!isJson(response)) {
    const type = response.headers.get("content-type") ?? "no content type";
    throw new ApiError("not-json", `Expected JSON from ${path} but received ${type} (status ${response.status}).`, path, response.status);
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError("invalid-json", `The response from ${path} is not valid JSON.`, path, response.status);
  }
  if (!response.ok) {
    const raw = (body as { message?: unknown; detail?: unknown } | null)?.message ?? (body as { detail?: unknown } | null)?.detail;
    const message = typeof raw === "string" && raw ? raw : `Request to ${path} failed with status ${response.status}.`;
    throw new ApiError("http", message, path, response.status);
  }
  return body as T;
}

/** Joins a folder relative to an approved experiment root. The server expects the absolute result. */
export function workspacePath(root: string, relative: string): string {
  return joinRootPath(root, relative);
}

export function listExperiments(options: RequestOptions = {}): Promise<ExperimentList> {
  return getJson<ExperimentList>("/v1/experiments", options);
}

export function createExperiment(request: ExperimentRequest, options: RequestOptions = {}): Promise<ExperimentEntry & { trust_notice: string }> {
  return sendJson("POST", "/v1/experiments", request, options);
}

export async function revokeExperiment(contextId: string, options: RequestOptions = {}): Promise<ExperimentRecord> {
  const path = `/v1/experiments/${safeId(contextId)}`;
  return (await sendJson<{ experiment: ExperimentRecord }>("DELETE", path, undefined, options)).experiment;
}

/** Issues a bearer credential bound to one active context. The token is in this response only. */
export async function issueBoundCredential(
  contextId: string,
  scopes: BearerScope[],
  label: string,
  options: RequestOptions = {},
): Promise<IssuedCredential> {
  const body = { scopes, label, experiment_context: safeId(contextId) };
  return sendJson<IssuedCredential>("POST", "/v1/credentials", body, options);
}
