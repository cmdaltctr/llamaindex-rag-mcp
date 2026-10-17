/**
 * Writes, each declaring the query keys it invalidates. Answers and searches
 * are mutations too, because each submission is a fresh request, but they
 * change nothing on the server and invalidate nothing.
 */
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useApi } from "./ApiProvider";
import type { ApiClient } from "./client";
import {
  answerCollection,
  changeProfile,
  deleteDocuments,
  ingestPath,
  searchCollection,
  setDisplayName,
  uploadFile,
  type ConfirmStep,
  type DeleteSelector,
  type Profile,
  type QueryControls,
} from "./documents";
import {
  saveLayout,
  saveRevision,
  submitRun,
  validatePipeline,
  type GraphDocument,
  type GraphLayout,
  type JsonValue,
} from "./pipelines";
import { createProfile, deleteProfile, updateProfile, type ProfileCreateInput, type ProfileUpdateInput } from "./profiles";
import { jobQuery, queryKeys } from "./queries";
import { cancelRunRecord } from "./runs";

/**
 * The collection list and counts, and every collection's documents: their
 * keys sit under `["collections"]`, so one prefix refreshes what each view shows.
 */
function invalidateCollections(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: queryKeys.collections() });
}

export function useUploadFile() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadFile(api, file),
    onSuccess: () => invalidateCollections(queryClient),
  });
}

const JOB_POLL_MS = 1000;
const JOB_WATCH_LIMIT_MS = 30 * 60 * 1000;

/**
 * Follows an ingest job until it ends, then refreshes the collections. It is
 * started with the job and owned by the cache, not by a view, so the counts
 * update in every view even when the user has left the page that started it.
 * Any outcome ends the watch, including a job that can no longer be read.
 */
async function watchIngestJob(queryClient: QueryClient, api: ApiClient, jobId: string): Promise<void> {
  const deadline = Date.now() + JOB_WATCH_LIMIT_MS;
  try {
    while (Date.now() < deadline) {
      const job = await queryClient.fetchQuery({ ...jobQuery(api, jobId), staleTime: 0 });
      if (job.status === "completed" || job.status === "failed") return;
      await new Promise((resolve) => setTimeout(resolve, JOB_POLL_MS));
    }
  } catch {
    // The job is gone or the server stopped: what it changed is still worth reading again.
  } finally {
    await invalidateCollections(queryClient);
  }
}

/** Starts an ingest job and watches it to its end in the background. */
export function useIngestPath() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { path: string; collection: string }) => ingestPath(api, input.path, input.collection),
    onSuccess: (job) => void watchIngestJob(queryClient, api, job.job_id),
  });
}

/**
 * Shows one ingest job. `watchIngestJob` is the only poller and keeps this
 * entry current, so this observer never polls on its own.
 */
export function useIngestJob(jobId: string | null) {
  const api = useApi();
  return useQuery({ ...jobQuery(api, jobId ?? ""), refetchInterval: false, staleTime: Infinity, enabled: jobId !== null });
}

export function useDeleteDocuments(collection: string) {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { selector: DeleteSelector; step: ConfirmStep }) => deleteDocuments(api, collection, input.selector, input.step),
    onSuccess: (_result, input) => ("preview" in input.step ? undefined : invalidateCollections(queryClient)),
  });
}

export function useChangeProfile(collection: string) {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { profile: Profile; step: ConfirmStep }) => changeProfile(api, collection, input.profile, input.step),
    onSuccess: (_result, input) => ("preview" in input.step ? undefined : invalidateCollections(queryClient)),
  });
}

/** Sets or clears the display name of one collection, then refreshes every view that shows it. */
export function useSetDisplayName(collection: string) {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (displayName: string) => setDisplayName(api, collection, displayName),
    onSuccess: () => invalidateCollections(queryClient),
  });
}

/** Marks answer mutations, so a view can ask whether any answer is still pending. */
export const ANSWER_MUTATION_KEY = ["answer"] as const;

export function useAnswer(collection: string) {
  const api = useApi();
  return useMutation({ mutationKey: ANSWER_MUTATION_KEY, mutationFn: (controls: QueryControls) => answerCollection(api, collection, controls) });
}

export function useSearch(collection: string) {
  const api = useApi();
  return useMutation({ mutationFn: (controls: QueryControls) => searchCollection(api, collection, controls) });
}

/** A revision save also refreshes the profiles, because it can change readiness and which collections it affects. */
export function useSaveRevision(pipelineId: string) {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (document: GraphDocument) => saveRevision(api, pipelineId, document),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.pipelines() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.profiles() }),
      ]),
  });
}

/** `queryKeys.profiles()` is the prefix of every profile entry, so one call refreshes the list and each open profile. */
function invalidateProfiles(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: queryKeys.profiles() });
}

export function useCreateProfile() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ProfileCreateInput) => createProfile(api, input),
    onSuccess: () => invalidateProfiles(queryClient),
  });
}

export function useUpdateProfile(profileId: string) {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ProfileUpdateInput) => updateProfile(api, profileId, input),
    onSuccess: () => invalidateProfiles(queryClient),
  });
}

export function useDeleteProfile(profileId: string) {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteProfile(api, profileId),
    onSuccess: () => invalidateProfiles(queryClient),
  });
}

/** A layout save changes the pipeline record only. It never creates a revision. */
export function useSaveLayout(pipelineId: string) {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (layout: GraphLayout) => saveLayout(api, pipelineId, layout),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.pipelines() }),
  });
}

/** A check of a draft changes nothing on the server, so it invalidates nothing. */
export function useValidatePipeline() {
  const api = useApi();
  return useMutation({
    mutationFn: (input: { document: GraphDocument; inputs?: Record<string, JsonValue> }) =>
      validatePipeline(api, input.document, input.inputs === undefined ? {} : { inputs: input.inputs }),
  });
}

/** Submitting or cancelling a run makes every run list stale. */
export function useSubmitRun() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { revisionId: string; inputs: Record<string, JsonValue> }) => submitRun(api, input.revisionId, input.inputs),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.allRuns() }),
  });
}

export function useCancelRun() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => cancelRunRecord(api, runId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.allRuns() }),
  });
}
