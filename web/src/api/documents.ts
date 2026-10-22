/**
 * Typed client for the document routes of the local `/v1` API.
 *
 * Shapes follow `src/omrs/transports/api/routes/documents.py`, `jobs.py`,
 * `inspection.py`, `admin.py` and `foundation.py` (roots, uploads,
 * session). Every function takes the `ApiClient` first, which owns the
 * transport checks: JSON content type, valid JSON and the error envelope.
 *
 * Omitted search and answer controls are sent as `null`, so the collection
 * profile decides them on the server.
 */
import { ApiError, ClientRefusal, type ApiClient, type CallOptions } from "./client";

export type JsonObject = { [key: string]: unknown };

/** The vector database behind a collection: registered backend name and its display label. */
export interface VectorStoreInfo {
  name: string;
  label: string;
}

export interface CollectionInfo {
  name: string;
  document_count: number;
  chunk_count: number;
  /** Profile stored in the collection metadata; `null` when none is stored or it cannot be read. */
  profile: string | null;
  /** Label the user gave the collection; `null` when none is set. The collection name stays `name`. */
  display_name: string | null;
  store: VectorStoreInfo;
}

/** Reply of the display-name route: `display_name` is `null` after a clear. */
export interface DisplayNameResult {
  collection: string;
  display_name: string | null;
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

/** Per-stage timings and call counts, sent only when the request asked for diagnostics. */
export interface AnswerDiagnostics {
  retrieval_ms: number;
  generation_ms: number;
  completion_calls: number;
  /** Present only when claim verification ran. */
  verification_ms?: number;
  /** Judge completions, one per cited sentence. Present only when claim verification ran. */
  verification_calls?: number;
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
  diagnostics?: AnswerDiagnostics;
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

/** A profile ID: a built-in name or the ID of a user profile from `GET /v1/profiles`. */
export type Profile = string;

/** A preview request, or a confirmation that carries the preview token. */
export type ConfirmStep = { preview: true } | { token: string };

/** Encodes one path segment and refuses empty, dot and separator-bearing values. */
function segment(value: string): string {
  if (value === "" || value === "." || value === ".." || /[/\\]/.test(value) || value.includes("\u0000")) {
    throw new ApiError("invalid-path", `Refused an unsafe path segment: ${JSON.stringify(value)}`, value);
  }
  return encodeURIComponent(value);
}

export function collectionPath(collection: string, rest = ""): string {
  return `/v1/collections/${segment(collection)}${rest}`;
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

export function listCollections(api: ApiClient, options: CallOptions = {}): Promise<CollectionInfo[]> {
  return api.request<CollectionInfo[]>("GET", "/v1/collections", { signal: options.signal });
}

export async function listDocuments(api: ApiClient, collection: string, options: CallOptions = {}): Promise<DocumentInfo[]> {
  return api.request<DocumentInfo[]>("GET", collectionPath(collection, "/documents"), { signal: options.signal });
}

export async function getChunk(
  api: ApiClient,
  collection: string,
  chunkId: string,
  window: number,
  options: CallOptions = {},
): Promise<ChunkInspection> {
  const size = Math.max(0, Math.min(5, Math.trunc(window)));
  return api.request<ChunkInspection>("GET", collectionPath(collection, `/chunks/${segment(chunkId)}`), {
    query: { window: size },
    signal: options.signal,
  });
}

export async function listRoots(api: ApiClient, options: CallOptions = {}): Promise<Root[]> {
  return (await api.request<{ roots: Root[] }>("GET", "/v1/roots", { signal: options.signal })).roots;
}

export function getSession(api: ApiClient, options: CallOptions = {}): Promise<SessionInfo> {
  return api.request<SessionInfo>("GET", "/v1/session", { signal: options.signal });
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

/** The body of both answer routes. Chat shows the judge call count, so it always asks for diagnostics. */
export function answerBody(controls: QueryControls) {
  return { ...controlsBody(controls), diagnostics: true };
}

export async function searchCollection(
  api: ApiClient,
  collection: string,
  controls: QueryControls,
  options: CallOptions = {},
): Promise<SearchHit[]> {
  return api.request<SearchHit[]>("POST", collectionPath(collection, "/search"), {
    body: controlsBody(controls),
    signal: options.signal,
  });
}

export async function answerCollection(
  api: ApiClient,
  collection: string,
  controls: QueryControls,
  options: CallOptions = {},
): Promise<AnswerResult> {
  return api.request<AnswerResult>("POST", collectionPath(collection, "/answer"), {
    body: answerBody(controls),
    signal: options.signal,
  });
}

// ── Preview-bound actions ───────────────────────────────────────────────

export async function deleteDocuments(
  api: ApiClient,
  collection: string,
  selector: DeleteSelector,
  step: ConfirmStep,
  options: CallOptions = {},
): Promise<DeleteResult> {
  const extra = "preview" in step ? { dry_run: true } : { confirmation_token: step.token };
  return api.request<DeleteResult>("DELETE", collectionPath(collection, "/documents"), {
    body: { ...selector, ...extra },
    signal: options.signal,
  });
}

export async function changeProfile(
  api: ApiClient,
  collection: string,
  profile: Profile,
  step: ConfirmStep,
  options: CallOptions = {},
): Promise<ProfilePreview | ProfileChangeResult> {
  const extra = "preview" in step ? { confirm: false } : { confirm: true, confirmation_token: step.token };
  return api.request<ProfilePreview | ProfileChangeResult>("PATCH", collectionPath(collection, "/profile"), {
    body: { profile, ...extra },
    signal: options.signal,
  });
}

/** Sets the display name of a collection. An empty value clears it. */
export async function setDisplayName(
  api: ApiClient,
  collection: string,
  displayName: string,
  options: CallOptions = {},
): Promise<DisplayNameResult> {
  return api.request<DisplayNameResult>("PATCH", collectionPath(collection, "/display-name"), {
    body: { display_name: displayName },
    signal: options.signal,
  });
}

// ── Uploads and jobs ────────────────────────────────────────────────────

/** Asks the server to check the name, type and size, then streams the raw bytes. */
export async function uploadFile(api: ApiClient, file: File, options: CallOptions = {}): Promise<UploadRecord> {
  await api.request("POST", "/v1/uploads/preflight", { body: { name: file.name, size: file.size }, signal: options.signal });
  const { upload } = await api.request<{ upload: UploadRecord }>("POST", "/v1/uploads", {
    body: file,
    headers: { "Content-Type": "application/octet-stream", "X-Upload-Name": encodeURIComponent(file.name) },
    signal: options.signal,
  });
  return upload;
}

export function ingestPath(api: ApiClient, path: string, collection: string, options: CallOptions = {}): Promise<Job> {
  return api.request<Job>("POST", "/v1/ingestions", { body: { path, collection }, signal: options.signal });
}

export async function getJob(api: ApiClient, jobId: string, options: CallOptions = {}): Promise<Job> {
  return api.request<Job>("GET", `/v1/jobs/${segment(jobId)}`, { signal: options.signal });
}

/**
 * Joins a path relative to an approved root. Absolute paths, home shortcuts,
 * drive letters and `..` segments are refused, so the browser never names an
 * arbitrary server path. The server checks the result against its grants again.
 */
export function joinRootPath(root: string, relative: string): string {
  const trimmed = relative.trim();
  if (trimmed === "" || trimmed.includes("\u0000")) throw new ClientRefusal("Enter a path relative to the selected folder.");
  if (/^([/\\~]|[A-Za-z]:)/.test(trimmed)) {
    throw new ClientRefusal("Use a path relative to the selected folder, not an absolute path.");
  }
  const parts = trimmed.split(/[/\\]+/).filter((part) => part !== "" && part !== ".");
  if (parts.includes("..")) throw new ClientRefusal("The path must stay inside the selected folder.");
  if (parts.length === 0) throw new ClientRefusal("Enter a path relative to the selected folder.");
  const separator = root.includes("\\") && !root.includes("/") ? "\\" : "/";
  const base = root.replace(/[/\\]+$/, "");
  return [base, ...parts].join(separator);
}
