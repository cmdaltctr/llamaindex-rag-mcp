/**
 * Typed client for the graph and run routes of the local `/v1` API.
 *
 * Shapes follow `src/omrg/transports/api/routes_graphs.py` and
 * `routes_runs.py`. GET requests reuse `getJson`. Writes use the same checks:
 * JSON content type, valid JSON, and the error envelope. A 422 envelope with
 * `issues` becomes `PipelineIssuesError`, so the canvas can mark nodes and ports.
 */
import { ApiError, getJson, type RequestOptions } from "./client";

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export type Cardinality = "one" | "optional" | "many";

export interface PortType {
  kind: string;
  provenance: string[];
  score_kinds: string[] | null;
  embedding_identity: boolean;
  reader_declarations: string[];
}

export interface PortDescriptor {
  name: string;
  type: PortType;
  cardinality: Cardinality;
  description: string;
}

export interface JsonSchema {
  type?: string | string[];
  title?: string;
  description?: string;
  anyOf?: JsonSchema[];
  enum?: JsonValue[];
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  default?: JsonValue;
  properties?: Record<string, JsonSchema>;
  additionalProperties?: boolean | JsonSchema;
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
}

export interface OperationDescriptor {
  operation_id: string;
  version: number;
  title: string;
  family: string;
  description: string;
  parameters: JsonSchema;
  inputs: PortDescriptor[];
  outputs: PortDescriptor[];
  capabilities: string[];
  effect: string;
  bypass: { input_port: string; output_port: string } | null;
  collection_param: string | null;
  lever_params: Record<string, string>;
  free_text_params: string[];
  index_shaping: boolean;
  available: boolean;
  unavailable_reasons: string[];
}

export interface PortRef {
  node: string;
  port: string;
}

export interface EdgeSpec {
  source: PortRef;
  target: PortRef;
}

export interface NodeSpec {
  id: string;
  operation: string;
  version?: number | null;
  params?: Record<string, JsonValue>;
  enabled?: boolean;
}

export interface GraphInput {
  name: string;
  kind: string;
  targets: PortRef[];
  required?: boolean;
}

export interface GraphOutput {
  name: string;
  source: PortRef;
}

/** The execution document. Changing it changes execution identity. */
export interface GraphDocument {
  schema_version: number;
  nodes: NodeSpec[];
  edges?: EdgeSpec[];
  inputs?: GraphInput[];
  outputs?: GraphOutput[];
  profile?: string | null;
  collection?: string | null;
  overrides?: Record<string, JsonValue>;
}

/** Presentation only. Saving it never creates a revision. */
export interface GraphLayout {
  title?: string;
  positions?: Record<string, { x: number; y: number }>;
  viewport?: { x: number; y: number; zoom: number };
  selection?: string[];
}

export interface PipelineRecord {
  pipeline_id: string;
  title: string;
  current_revision_id: string | null;
  layout: GraphLayout;
  created_at: string;
  updated_at: string;
}

export interface RevisionRecord {
  revision_id: string;
  pipeline_id: string;
  revision_number: number;
  content_hash: string;
  schema_version: number;
  document: GraphDocument;
  created_at: string;
}

export interface RunRecord {
  run_id: string;
  status: string;
  revision_id?: string;
  failure?: unknown;
  [key: string]: unknown;
}

export interface ValidationIssue {
  code: string;
  message: string;
  node_id?: string | null;
  port?: string | null;
  edge?: string | null;
  lever?: string | null;
}

export interface EffectiveControl {
  lever: string;
  value: JsonValue;
  source: string;
  detail: string;
}

export interface ValidationReport {
  valid: true;
  admitted: boolean;
  order: string[];
  nodes?: { node_id: string; controls: EffectiveControl[] }[];
}

/** A refused graph or run with structured issues (HTTP 422). */
export class PipelineIssuesError extends ApiError {
  readonly issues: ValidationIssue[];

  constructor(message: string, path: string, status: number, issues: ValidationIssue[]) {
    super("http", message, path, status);
    this.name = "PipelineIssuesError";
    this.issues = issues;
  }
}

const ID_PATTERN = /^[A-Za-z0-9_-]+$/;

/** Builds `/v1/...` from fixed segments and identifiers. Refuses identifiers that change the path. */
function apiPath(template: TemplateStringsArray, ...ids: string[]): string {
  for (const id of ids) {
    if (!ID_PATTERN.test(id)) throw new ApiError("invalid-path", `Refused an unsafe identifier: ${id}`, template.join("?"));
  }
  return template.reduce((path, part, index) => path + part + (ids[index] ?? ""), "");
}

function isJson(response: Response): boolean {
  const type = response.headers.get("content-type")?.split(";")[0]?.trim().toLowerCase() ?? "";
  return type === "application/json" || type.endsWith("+json");
}

function issuesOf(body: unknown): ValidationIssue[] | null {
  if (typeof body !== "object" || body === null) return null;
  const issues = (body as { issues?: unknown }).issues;
  return Array.isArray(issues) ? (issues as ValidationIssue[]) : null;
}

async function sendJson<T>(method: "POST" | "PUT", path: string, payload: unknown, options: RequestOptions): Promise<T> {
  const fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
  let response: Response;
  try {
    response = await fetchImpl(path, {
      method,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
      signal: options.signal,
    });
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
    const raw = (body as { message?: unknown } | null)?.message;
    const message = typeof raw === "string" && raw ? raw : `Request to ${path} failed with status ${response.status}.`;
    const issues = issuesOf(body);
    if (issues !== null) throw new PipelineIssuesError(message, path, response.status, issues);
    throw new ApiError("http", message, path, response.status);
  }
  return body as T;
}

export async function listOperations(options: RequestOptions = {}): Promise<OperationDescriptor[]> {
  return (await getJson<{ operations: OperationDescriptor[] }>("/v1/pipeline-operations", options)).operations;
}

export async function listPipelines(options: RequestOptions = {}): Promise<PipelineRecord[]> {
  return (await getJson<{ pipelines: PipelineRecord[] }>("/v1/pipelines", options)).pipelines;
}

export async function createPipeline(title: string, layout: GraphLayout, options: RequestOptions = {}): Promise<PipelineRecord> {
  return (await sendJson<{ pipeline: PipelineRecord }>("POST", "/v1/pipelines", { title, layout }, options)).pipeline;
}

export async function getPipeline(
  pipelineId: string,
  options: RequestOptions = {},
): Promise<{ pipeline: PipelineRecord; current_revision: RevisionRecord | null }> {
  return getJson(apiPath`/v1/pipelines/${pipelineId}`, options);
}

export async function saveLayout(pipelineId: string, layout: GraphLayout, options: RequestOptions = {}): Promise<PipelineRecord> {
  const path = apiPath`/v1/pipelines/${pipelineId}/layout`;
  return (await sendJson<{ pipeline: PipelineRecord }>("PUT", path, { layout }, options)).pipeline;
}

export async function saveRevision(
  pipelineId: string,
  document: GraphDocument,
  options: RequestOptions = {},
): Promise<{ revision: RevisionRecord; created: boolean }> {
  const path = apiPath`/v1/pipelines/${pipelineId}/revisions`;
  const body = await sendJson<{ revision: RevisionRecord; created: boolean }>("POST", path, { document }, options);
  return { revision: body.revision, created: body.created };
}

/** Draft check without `inputs`; admission check (with effective controls) with `inputs`. */
export async function validatePipeline(
  document: GraphDocument,
  check: { inputs?: Record<string, JsonValue>; collection?: string },
  options: RequestOptions = {},
): Promise<ValidationReport> {
  return sendJson<ValidationReport>("POST", "/v1/pipelines/validate", { document, ...check }, options);
}

export async function submitRun(revisionId: string, inputs: Record<string, JsonValue>, options: RequestOptions = {}): Promise<RunRecord> {
  return (await sendJson<{ run: RunRecord }>("POST", "/v1/runs", { revision_id: revisionId, inputs }, options)).run;
}

export async function cancelRun(runId: string, options: RequestOptions = {}): Promise<RunRecord> {
  return (await sendJson<{ run: RunRecord }>("POST", apiPath`/v1/runs/${runId}/cancel`, {}, options)).run;
}

export async function getRun(runId: string, options: RequestOptions = {}): Promise<RunRecord> {
  return (await getJson<{ run: RunRecord }>(apiPath`/v1/runs/${runId}`, options)).run;
}
