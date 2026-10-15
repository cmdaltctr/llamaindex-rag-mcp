/**
 * Typed client for the experiment context routes and bound credentials.
 *
 * Shapes follow `src/omrg/transports/api/routes_experiments.py` and
 * `POST /v1/credentials` in `routes.py`. Experiment refusals carry a stable
 * `code`; the user sees the server's `message`.
 */
import { joinRootPath } from "./documents";
import { ApiError, type ApiClient, type CallOptions } from "./client";

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

/** One directory below an approved root. A registered workspace is a leaf with a `context_id`. */
export interface FolderNode {
  name: string;
  path: string;
  workspace: string;
  context_id: string | null;
  children: FolderNode[];
}

export interface FolderRoot {
  root: string;
  tree: FolderNode[];
}

export interface ExperimentList {
  roots: string[];
  /** One directory tree per approved root, capped by the server at 500 nodes. */
  folders: FolderRoot[];
  experiments: ExperimentEntry[];
  trust_notice: string;
}

export interface CreatedFolder {
  root: string;
  path: string;
  name: string;
  /** Absolute path, ready to pass to `createExperiment`. */
  workspace: string;
}

export type ExperimentAction = "read" | "ingest";
export type BearerScope = "graph" | "read" | "run";

export interface ExperimentRequest {
  workspace: string;
  name: string;
  actions: ExperimentAction[];
  declared_factors?: string[];
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

/** Joins a folder relative to an approved experiment root. The server expects the absolute result. */
export function workspacePath(root: string, relative: string): string {
  return joinRootPath(root, relative);
}

export function listExperiments(api: ApiClient, options: CallOptions = {}): Promise<ExperimentList> {
  return api.request<ExperimentList>("GET", "/v1/experiments", { signal: options.signal });
}

export function createExperiment(
  api: ApiClient,
  request: ExperimentRequest,
  options: CallOptions = {},
): Promise<ExperimentEntry & { trust_notice: string }> {
  return api.request<ExperimentEntry & { trust_notice: string }>("POST", "/v1/experiments", {
    body: request,
    signal: options.signal,
  });
}

/**
 * Creates a folder below an approved root. `root` is needed only when the
 * server approved more than one. A refusal carries a stable `code` in
 * `ApiError.body`.
 */
export async function createExperimentFolder(
  api: ApiClient,
  request: { path: string; root?: string | null },
  options: CallOptions = {},
): Promise<CreatedFolder> {
  const body = { path: request.path, root: request.root ?? null };
  const response = await api.request<{ folder: CreatedFolder }>("POST", "/v1/experiment-folders", { body, signal: options.signal });
  return response.folder;
}

export async function revokeExperiment(api: ApiClient, contextId: string, options: CallOptions = {}): Promise<ExperimentRecord> {
  const path = `/v1/experiments/${safeId(contextId)}`;
  return (await api.request<{ experiment: ExperimentRecord }>("DELETE", path, { signal: options.signal })).experiment;
}

/** Issues a bearer credential bound to one active context. The token is in this response only. */
export async function issueBoundCredential(
  api: ApiClient,
  contextId: string,
  scopes: BearerScope[],
  label: string,
  options: CallOptions = {},
): Promise<IssuedCredential> {
  const body = { scopes, label, experiment_context: safeId(contextId) };
  return api.request<IssuedCredential>("POST", "/v1/credentials", { body, signal: options.signal });
}
