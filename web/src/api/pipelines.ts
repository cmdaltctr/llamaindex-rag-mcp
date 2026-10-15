/**
 * Typed client for the graph and run routes of the local `/v1` API.
 *
 * Shapes follow `src/omrg/transports/api/routes_graphs.py` and
 * `routes_runs.py`. Every function takes the `ApiClient` first. An error
 * envelope with `issues` becomes `PipelineIssuesError`, so the canvas can mark
 * nodes and ports.
 */
import { ApiError, type ApiClient, type CallOptions, type RequestInput } from "./client";

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

function issuesOf(body: unknown): ValidationIssue[] | null {
  if (typeof body !== "object" || body === null) return null;
  const issues = (body as { issues?: unknown }).issues;
  return Array.isArray(issues) ? (issues as ValidationIssue[]) : null;
}

/** One request through the client. A refusal that carries `issues` becomes `PipelineIssuesError`. */
async function call<T>(api: ApiClient, method: "GET" | "POST" | "PUT", path: string, input: RequestInput): Promise<T> {
  try {
    return await api.request<T>(method, path, input);
  } catch (error) {
    if (error instanceof ApiError && error.kind === "http") {
      const issues = issuesOf(error.body);
      if (issues !== null) throw new PipelineIssuesError(error.message, error.path, error.status ?? 0, issues);
    }
    throw error;
  }
}

export async function listOperations(api: ApiClient, options: CallOptions = {}): Promise<OperationDescriptor[]> {
  return (await api.request<{ operations: OperationDescriptor[] }>("GET", "/v1/pipeline-operations", { signal: options.signal })).operations;
}

export async function listPipelines(api: ApiClient, options: CallOptions = {}): Promise<PipelineRecord[]> {
  return (await api.request<{ pipelines: PipelineRecord[] }>("GET", "/v1/pipelines", { signal: options.signal })).pipelines;
}

export async function createPipeline(
  api: ApiClient,
  title: string,
  layout: GraphLayout,
  options: CallOptions = {},
): Promise<PipelineRecord> {
  const body = { title, layout };
  return (await call<{ pipeline: PipelineRecord }>(api, "POST", "/v1/pipelines", { body, signal: options.signal })).pipeline;
}

export async function getPipeline(
  api: ApiClient,
  pipelineId: string,
  options: CallOptions = {},
): Promise<{ pipeline: PipelineRecord; current_revision: RevisionRecord | null }> {
  return api.request("GET", apiPath`/v1/pipelines/${pipelineId}`, { signal: options.signal });
}

export async function getRevision(
  api: ApiClient,
  pipelineId: string,
  revisionId: string,
  options: CallOptions = {},
): Promise<RevisionRecord> {
  const path = apiPath`/v1/pipelines/${pipelineId}/revisions/${revisionId}`;
  return (await api.request<{ revision: RevisionRecord }>("GET", path, { signal: options.signal })).revision;
}

export async function saveLayout(api: ApiClient, pipelineId: string, layout: GraphLayout, options: CallOptions = {}): Promise<PipelineRecord> {
  const path = apiPath`/v1/pipelines/${pipelineId}/layout`;
  return (await call<{ pipeline: PipelineRecord }>(api, "PUT", path, { body: { layout }, signal: options.signal })).pipeline;
}

export async function saveRevision(
  api: ApiClient,
  pipelineId: string,
  document: GraphDocument,
  options: CallOptions = {},
): Promise<{ revision: RevisionRecord; created: boolean }> {
  const path = apiPath`/v1/pipelines/${pipelineId}/revisions`;
  const saved = await call<{ revision: RevisionRecord; created: boolean }>(api, "POST", path, {
    body: { document },
    signal: options.signal,
  });
  return { revision: saved.revision, created: saved.created };
}

/** Draft check without `inputs`; admission check (with effective controls) with `inputs`. */
export async function validatePipeline(
  api: ApiClient,
  document: GraphDocument,
  check: { inputs?: Record<string, JsonValue>; collection?: string },
  options: CallOptions = {},
): Promise<ValidationReport> {
  return call<ValidationReport>(api, "POST", "/v1/pipelines/validate", { body: { document, ...check }, signal: options.signal });
}

export async function submitRun(
  api: ApiClient,
  revisionId: string,
  inputs: Record<string, JsonValue>,
  options: CallOptions = {},
): Promise<RunRecord> {
  const body = { revision_id: revisionId, inputs };
  return (await call<{ run: RunRecord }>(api, "POST", "/v1/runs", { body, signal: options.signal })).run;
}

/** A canonical template from `GET /v1/pipeline-templates`: an editable starting point, not an executable revision. */
export interface PipelineTemplate {
  name: string;
  title: string;
  description: string;
  standard_operation: string;
  document: GraphDocument;
  outputs: { name: string; description: string }[];
}

export async function listTemplates(api: ApiClient, options: CallOptions = {}): Promise<PipelineTemplate[]> {
  return (await api.request<{ templates: PipelineTemplate[] }>("GET", "/v1/pipeline-templates", { signal: options.signal })).templates;
}
