/**
 * Every server read, declared once with `queryOptions` and a hierarchical
 * key. `@tanstack/react-query` owns server data in the browser: views never
 * fetch on their own, so a change invalidates the same keys everywhere.
 */
import { MutationCache, QueryCache, QueryClient, queryOptions } from "@tanstack/react-query";
import { ApiError, type ApiClient } from "./client";
import { getChunk, getJob, getSession, listCollections, listDocuments, listRoots } from "./documents";
import { listExperiments } from "./experiments";
import { listIntegrations } from "./integrations";
import { getPipeline, getRevision, listOperations, PipelineIssuesError, validatePipeline, type GraphDocument, type NodeControls } from "./pipelines";
import { listPlugins } from "./plugins";
import { getProfile, listProfiles } from "./profiles";
import { getRunArtefact, getRunRecord, getRunResult, listRuns } from "./runs";
import { getConnections, getHealth, getMcpState, getUploadLimit, getWebPort } from "./settings";

declare module "@tanstack/react-query" {
  interface Register {
    defaultError: ApiError;
  }
}

export interface RunFilters {
  statuses?: readonly string[];
  pipelineId?: string;
  limit?: number;
}

export const queryKeys = {
  collections: () => ["collections"] as const,
  documents: (collection: string) => ["collections", collection, "documents"] as const,
  chunk: (collection: string, chunkId: string, window: number) => ["collections", collection, "chunks", chunkId, window] as const,
  pipelines: () => ["pipelines"] as const,
  pipeline: (id: string) => ["pipelines", id] as const,
  revision: (pipelineId: string, revisionId: string) => ["pipelines", pipelineId, "revisions", revisionId] as const,
  profiles: () => ["profiles"] as const,
  profile: (id: string) => ["profiles", id] as const,
  operations: () => ["pipeline-operations"] as const,
  draftCheck: (document: string) => ["pipeline-draft-checks", document] as const,
  allRuns: () => ["runs"] as const,
  runs: (filters: RunFilters) => ["runs", filters] as const,
  run: (id: string) => ["runs", id] as const,
  runResult: (id: string) => ["runs", id, "result"] as const,
  runEvents: (id: string) => ["runs", id, "events"] as const,
  runArtefact: (id: string, name: string) => ["runs", id, "artefacts", name] as const,
  experiments: () => ["experiments"] as const,
  plugins: () => ["plugins"] as const,
  roots: () => ["roots"] as const,
  session: () => ["session"] as const,
  health: () => ["health"] as const,
  connections: () => ["connections"] as const,
  mcp: () => ["mcp"] as const,
  webPort: () => ["settings", "web-port"] as const,
  uploadLimit: () => ["settings", "upload-limit"] as const,
  integrations: () => ["integrations"] as const,
  job: (id: string) => ["jobs", id] as const,
};

/** How long a read counts as fresh, so moving between views does not refetch shared data. */
export const STALE_MS = 30_000;

/** One retry for a `network` failure only; an HTTP answer is never retried. */
export function shouldRetry(failureCount: number, error: Error): boolean {
  return error instanceof ApiError && error.kind === "network" && failureCount < 1;
}

/** The one `QueryClient` setup. Tests pass `retry: false` and nothing else changes. */
export function createQueryClient(overrides: { retry?: false } = {}): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache(),
    mutationCache: new MutationCache(),
    defaultOptions: {
      queries: {
        retry: overrides.retry ?? shouldRetry,
        refetchOnWindowFocus: false,
        staleTime: STALE_MS,
      },
      mutations: { retry: false },
    },
  });
}

export const collectionsQuery = (api: ApiClient) =>
  queryOptions({ queryKey: queryKeys.collections(), queryFn: ({ signal }) => listCollections(api, { signal }) });

export const documentsQuery = (api: ApiClient, collection: string) =>
  queryOptions({ queryKey: queryKeys.documents(collection), queryFn: ({ signal }) => listDocuments(api, collection, { signal }) });

export const chunkQuery = (api: ApiClient, collection: string, chunkId: string, window: number) =>
  queryOptions({
    queryKey: queryKeys.chunk(collection, chunkId, window),
    queryFn: ({ signal }) => getChunk(api, collection, chunkId, window, { signal }),
  });

export const pipelineQuery = (api: ApiClient, id: string) =>
  queryOptions({ queryKey: queryKeys.pipeline(id), queryFn: ({ signal }) => getPipeline(api, id, { signal }) });

export const revisionQuery = (api: ApiClient, pipelineId: string, revisionId: string) =>
  queryOptions({
    queryKey: queryKeys.revision(pipelineId, revisionId),
    queryFn: ({ signal }) => getRevision(api, pipelineId, revisionId, { signal }),
    staleTime: Infinity, // A revision never changes.
  });

/** Built-in profiles first, then user profiles. Items carry no standard graphs; read `profileQuery` for those. */
export const profilesQuery = (api: ApiClient) =>
  queryOptions({ queryKey: queryKeys.profiles(), queryFn: ({ signal }) => listProfiles(api, { signal }) });

export const profileQuery = (api: ApiClient, id: string) =>
  queryOptions({ queryKey: queryKeys.profile(id), queryFn: ({ signal }) => getProfile(api, id, { signal }) });

export const operationsQuery =(api: ApiClient) =>
  queryOptions({ queryKey: queryKeys.operations(), queryFn: ({ signal }) => listOperations(api, { signal }) });

export const runsQuery = (api: ApiClient, filters: RunFilters = {}) =>
  queryOptions({ queryKey: queryKeys.runs(filters), queryFn: ({ signal }) => listRuns(api, filters, { signal }) });

export const runQuery = (api: ApiClient, id: string) =>
  queryOptions({ queryKey: queryKeys.run(id), queryFn: ({ signal }) => getRunRecord(api, id, { signal }) });

export const runResultQuery = (api: ApiClient, id: string) =>
  queryOptions({ queryKey: queryKeys.runResult(id), queryFn: ({ signal }) => getRunResult(api, id, { signal }) });

/** One stored artefact. It never changes once written, so it stays fresh. */
export const runArtefactQuery = (api: ApiClient, runId: string, name: string) =>
  queryOptions({
    queryKey: queryKeys.runArtefact(runId, name),
    queryFn: ({ signal }) => getRunArtefact(api, runId, name, { signal }),
    staleTime: Infinity,
  });

export const experimentsQuery = (api: ApiClient) =>
  queryOptions({ queryKey: queryKeys.experiments(), queryFn: ({ signal }) => listExperiments(api, { signal }) });

export const pluginsQuery = (api: ApiClient) =>
  queryOptions({ queryKey: queryKeys.plugins(), queryFn: ({ signal }) => listPlugins(api, { signal }) });

export const rootsQuery = (api: ApiClient) =>
  queryOptions({ queryKey: queryKeys.roots(), queryFn: ({ signal }) => listRoots(api, { signal }) });

export const sessionQuery = (api: ApiClient) =>
  queryOptions({ queryKey: queryKeys.session(), queryFn: ({ signal }) => getSession(api, { signal }) });

export const healthQuery = (api: ApiClient) =>
  queryOptions({ queryKey: queryKeys.health(), queryFn: ({ signal }) => getHealth(api, { signal }) });

/** Provider endpoints, models, key state and roles. Sends no request to any provider. */
export const connectionsQuery = (api: ApiClient) =>
  queryOptions({ queryKey: queryKeys.connections(), queryFn: ({ signal }) => getConnections(api, { signal }) });

/**
 * The draft check of one graph document, given as JSON text, read for the
 * effective control values it reports. A refused draft is data: its 422 body
 * still carries the controls of the nodes the server could resolve.
 */
export const draftCheckQuery = (api: ApiClient, document: string) =>
  queryOptions({
    queryKey: queryKeys.draftCheck(document),
    queryFn: async ({ signal }): Promise<NodeControls[]> => {
      try {
        return (await validatePipeline(api, JSON.parse(document) as GraphDocument, {}, { signal })).nodes ?? [];
      } catch (error) {
        if (error instanceof PipelineIssuesError) return error.nodes ?? [];
        throw error;
      }
    },
  });

export const mcpQuery = (api: ApiClient) =>
  queryOptions({ queryKey: queryKeys.mcp(), queryFn: ({ signal }) => getMcpState(api, { signal }) });

export const webPortQuery = (api: ApiClient) =>
  queryOptions({ queryKey: queryKeys.webPort(), queryFn: ({ signal }) => getWebPort(api, { signal }) });

/** The per-file upload limit in force. Settings and the Knowledge Base read the same entry. */
export const uploadLimitQuery = (api: ApiClient) =>
  queryOptions({ queryKey: queryKeys.uploadLimit(), queryFn: ({ signal }) => getUploadLimit(api, { signal }) });

export const integrationsQuery = (api: ApiClient) =>
  queryOptions({ queryKey: queryKeys.integrations(), queryFn: ({ signal }) => listIntegrations(api, { signal }) });

const POLL_MS = 1000;

/** An ingest job, polled until it completes or fails. */
export const jobQuery = (api: ApiClient, jobId: string) =>
  queryOptions({
    queryKey: queryKeys.job(jobId),
    queryFn: ({ signal }) => getJob(api, jobId, { signal }),
    staleTime: 0,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "failed" ? false : POLL_MS;
    },
  });
