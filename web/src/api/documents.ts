/**
 * Typed client for the document routes of the local `/v1` API.
 *
 * Shapes follow `src/omrg/transports/api/routes_documents.py`, `routes_jobs.py`,
 * `routes_inspect.py`, `routes_admin.py` and `routes.py` (roots, uploads,
 * session). GET requests reuse `getJson`. Writes apply the same checks: JSON
 * content type, valid JSON and the error envelope message.
 *
 * Omitted search and answer controls are sent as `null`, so the collection
 * profile decides them on the server.
 */
import { ApiError, getJson, type RequestOptions } from "./client";

export type JsonObject = { [key: string]: unknown };

export interface CollectionInfo {
  name: string;
  document_count: number;
  chunk_count: number;
  /** Profile stored in the collection metadata; `null` when none is stored or it cannot be read. */
  profile: string | null;
}

export interface SessionInfo {
  kind: string;
  scopes: string[];
  /** Canonical workspace directory of this server; `null` only while the runtime is not started. */
  workspace: string | null;
}

/** `orphaned` is machine-local: true missing here, false present here, null unknown. */
export interface DocumentInfo {
  source: string;
  source_id: string | null;
  chunks: number;
  orphaned: boolean | null;
}

export interface Root {
  id: string;
  path: string;
  kind: "operator" | "managed";
}

export interface UploadRecord {
  id: string;
  name: string;
  size: number;
  sha256: string;
}

export interface Job {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  result: JsonObject | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface QueryControls {
  query: string;
  top_k?: number | null;
  rerank?: boolean | null;
  hybrid?: boolean | null;
  metadata_filter?: JsonObject | null;
}

export interface SearchHit {
  score?: number;
  score_kind?: string;
  source: string;
  page_label?: string | null;
  text: string;
  reranked: boolean;
  metadata: JsonObject;
  source_id: string | null;
  source_version: string | null;
  chunk_id: string | null;
  source_chunk_index: number | null;
  source_chunk_count: number | null;
  chunk_ids?: string[];
}

export interface Citation {
  ordinal: number;
  chunk_id: string | null;
  chunk_ids: string[];
  source_id: string | null;
  source_version: string | null;
  source: string | null;
  source_chunk_index: number | null;
  score?: number | null;
  score_kind?: string | null;
}

export interface Evidence extends Citation {
  text: string;
}

export type AnswerStatus = "ok" | "no_evidence" | "generation_unverified" | "unverified_claims" | "error";

export interface AnswerResult {
  status: AnswerStatus;
  query: string;
  answer: string | null;
  citations: Citation[];
  evidence: Evidence[];
  failure_stage: "retrieval" | "generation" | null;
  error: string | null;
  completion_source: string;
  verified?: boolean;
  unverified_claims?: { claim: string; verdict: string; ordinals: number[] }[];
  verification_skipped?: string;
}

export interface ChunkView {
  chunk_id: string | null;
  source_id: string | null;
  source_version: string | null;
  source_chunk_index: number | null;
  source_chunk_count: number | null;
  source: string | null;
  page_label: string | null;
  text: string;
  metadata: JsonObject;
}

export interface ChunkInspection {
  status: "ok";
  collection: string;
  text_format: "plain";
  chunk: ChunkView;
  previous: ChunkView[];
  next: ChunkView[];
}

export interface Confirmation {
  token: string;
  expires_at: string;
  expires_in: number;
  validity: "durable" | "process_local";
  warning: string | null;
}

export interface DeleteSelector {
  path?: string;
  metadata_filter?: JsonObject;
}

export interface DeleteResult {
  status: "ok";
  mode: "path" | "metadata" | "collection";
  collection: string;
  dry_run?: boolean;
  would_delete?: number;
  confirmation?: Confirmation;
  chunks_removed?: number;
}

export interface LeverImpact {
  lever: string;
  change: string;
  timing: "query-time" | "ingest-time";
}

export interface ProfilePreview {
  status: "preview";
  contract: {
    collection: string;
    new_profile: string;
    old_profile: string | null;
    chunk_count: number;
    lever_impacts: LeverImpact[];
    reingest_pointer: string;
  };
  confirm_required: true;
  confirmation?: Confirmation;
}

export interface ProfileChangeResult {
  status: "ok";
  collection: string;
  profile: string;
  chunk_count_unchanged: number;
}

export type Profile = "documents" | "codebase";

/** A preview request, or a confirmation that carries the preview token. */
export type ConfirmStep = { preview: true } | { token: string };

const JSON_HEADERS = { Accept: "application/json", "Content-Type": "application/json" };

/** Encodes one path segment and refuses empty, dot and separator-bearing values. */
function segment(value: string): string {
  if (value === "" || value === "." || value === ".." || /[/\\]/.test(value) || value.includes("\u0000")) {
    throw new ApiError("invalid-path", `Refused an unsafe path segment: ${JSON.stringify(value)}`, value);
  }
  return encodeURIComponent(value);
}

function collectionPath(collection: string, rest = ""): string {
  return `/v1/collections/${segment(collection)}${rest}`;
}

function isJson(response: Response): boolean {
  const type = response.headers.get("content-type")?.split(";")[0]?.trim().toLowerCase() ?? "";
  return type === "application/json" || type.endsWith("+json");
}

async function send<T>(method: string, path: string, init: RequestInit, options: RequestOptions): Promise<T> {
  const fetchImpl = options.fetchImpl ?? ((input, request) => fetch(input, request));
  let response: Response;
  try {
    response = await fetchImpl(path, { ...init, method, credentials: "same-origin", signal: options.signal });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new ApiError("network", `Could not reach the local server: ${detail}`, path);
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
    const message = (body as { message?: unknown } | null)?.message;
    const text = typeof message === "string" && message ? message : `Request to ${path} failed with status ${response.status}.`;
    throw new ApiError("http", text, path, response.status);
  }
  return body as T;
}

function sendJson<T>(method: string, path: string, payload: unknown, options: RequestOptions): Promise<T> {
  return send<T>(method, path, { headers: JSON_HEADERS, body: JSON.stringify(payload) }, options);
}

/** True when the server refused a confirmation because the preview is stale, used or expired. */
export function isStaleConfirmation(error: unknown): boolean {
  return error instanceof ApiError && error.kind === "http" && error.status === 409;
}

/** True when the server asked for a preview token that was not sent. */
export function isConfirmationRequired(error: unknown): boolean {
  return error instanceof ApiError && error.kind === "http" && error.status === 428;
}

// ── Listing and inspection ──────────────────────────────────────────────

export function listCollections(options: RequestOptions = {}): Promise<CollectionInfo[]> {
  return getJson<CollectionInfo[]>("/v1/collections", options);
}

export async function listDocuments(collection: string, options: RequestOptions = {}): Promise<DocumentInfo[]> {
  return getJson<DocumentInfo[]>(collectionPath(collection, "/documents"), options);
}

export async function getChunk(collection: string, chunkId: string, window: number, options: RequestOptions = {}): Promise<ChunkInspection> {
  const size = Math.max(0, Math.min(5, Math.trunc(window)));
  return getJson<ChunkInspection>(collectionPath(collection, `/chunks/${segment(chunkId)}?window=${size}`), options);
}

export async function listRoots(options: RequestOptions = {}): Promise<Root[]> {
  return (await getJson<{ roots: Root[] }>("/v1/roots", options)).roots;
}

export function getSession(options: RequestOptions = {}): Promise<SessionInfo> {
  return getJson("/v1/session", options);
}

// ── Search and answer ───────────────────────────────────────────────────

function controlsBody(controls: QueryControls) {
  return {
    query: controls.query,
    top_k: controls.top_k ?? null,
    rerank: controls.rerank ?? null,
    hybrid: controls.hybrid ?? null,
    metadata_filter: controls.metadata_filter ?? null,
  };
}

export async function searchCollection(collection: string, controls: QueryControls, options: RequestOptions = {}): Promise<SearchHit[]> {
  return sendJson("POST", collectionPath(collection, "/search"), controlsBody(controls), options);
}

export async function answerCollection(collection: string, controls: QueryControls, options: RequestOptions = {}): Promise<AnswerResult> {
  return sendJson("POST", collectionPath(collection, "/answer"), controlsBody(controls), options);
}

// ── Preview-bound actions ───────────────────────────────────────────────

export async function deleteDocuments(
  collection: string,
  selector: DeleteSelector,
  step: ConfirmStep,
  options: RequestOptions = {},
): Promise<DeleteResult> {
  const extra = "preview" in step ? { dry_run: true } : { confirmation_token: step.token };
  return sendJson("DELETE", collectionPath(collection, "/documents"), { ...selector, ...extra }, options);
}

export async function changeProfile(
  collection: string,
  profile: Profile,
  step: ConfirmStep,
  options: RequestOptions = {},
): Promise<ProfilePreview | ProfileChangeResult> {
  const extra = "preview" in step ? { confirm: false } : { confirm: true, confirmation_token: step.token };
  return sendJson("PATCH", collectionPath(collection, "/profile"), { profile, ...extra }, options);
}

// ── Uploads and jobs ────────────────────────────────────────────────────

/** Asks the server to check the name, type and size, then streams the raw bytes. */
export async function uploadFile(file: File, options: RequestOptions = {}): Promise<UploadRecord> {
  await sendJson("POST", "/v1/uploads/preflight", { name: file.name, size: file.size }, options);
  const headers = {
    Accept: "application/json",
    "Content-Type": "application/octet-stream",
    "X-Upload-Name": encodeURIComponent(file.name),
  };
  return (await send<{ upload: UploadRecord }>("POST", "/v1/uploads", { headers, body: file }, options)).upload;
}

export function ingestPath(path: string, collection: string, options: RequestOptions = {}): Promise<Job> {
  return sendJson("POST", "/v1/ingestions", { path, collection }, options);
}

export async function getJob(jobId: string, options: RequestOptions = {}): Promise<Job> {
  return getJson<Job>(`/v1/jobs/${segment(jobId)}`, options);
}

/**
 * Joins a path relative to an approved root. Absolute paths, home shortcuts,
 * drive letters and `..` segments are refused, so the browser never names an
 * arbitrary server path. The server checks the result against its grants again.
 */
export function joinRootPath(root: string, relative: string): string {
  const trimmed = relative.trim();
  if (trimmed === "" || trimmed.includes("\u0000")) throw new Error("Enter a path relative to the selected folder.");
  if (/^([/\\~]|[A-Za-z]:)/.test(trimmed)) {
    throw new Error("Use a path relative to the selected folder, not an absolute path.");
  }
  const parts = trimmed.split(/[/\\]+/).filter((part) => part !== "" && part !== ".");
  if (parts.includes("..")) throw new Error("The path must stay inside the selected folder.");
  if (parts.length === 0) throw new Error("Enter a path relative to the selected folder.");
  const separator = root.includes("\\") && !root.includes("/") ? "\\" : "/";
  const base = root.replace(/[/\\]+$/, "");
  return [base, ...parts].join(separator);
}
