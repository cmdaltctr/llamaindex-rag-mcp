/**
 * Writes for the Experiments area, each declaring the query keys it
 * invalidates. Secrets (a bound credential, an editor token) are returned to
 * the caller and held in component state only, so those mutations keep
 * nothing in the mutation cache (`gcTime: 0`).
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import {
  createExperiment,
  createExperimentFolder,
  issueBoundCredential,
  revokeExperiment,
  workspacePath,
  type BearerScope,
  type ExperimentAction,
} from "../api/experiments";
import { openEditor, recheckPlugin, registerPlugin, stopEditor, unregisterPlugin, type OpenRequest, type PluginList, type PluginState, type RegisterRequest } from "../api/plugins";
import { queryKeys } from "../api/queries";
import { retryRun } from "../api/runs";
import { refusalCode } from "./refusals";

export function useCreateFolder() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { path: string; root: string | null }) => createExperimentFolder(api, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.experiments() }),
  });
}

export interface SubExperimentInput {
  /** The folder's root and its path below that root. */
  root: string;
  parent: string;
  name: string;
  /** Sent to the folder route only when the server approves more than one root. */
  sendRoot: boolean;
  actions: ExperimentAction[];
  factors: string[];
}

/**
 * Creates the folder for a sub-experiment, then registers a context in it. A
 * folder that already exists (an earlier attempt stopped half-way) is used as it is.
 */
export function useCreateSubExperiment() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: SubExperimentInput) => {
      const path = `${input.parent}/${input.name}`;
      let workspace: string;
      try {
        workspace = (await createExperimentFolder(api, { path, root: input.sendRoot ? input.root : null })).workspace;
      } catch (error) {
        if (refusalCode(error) !== "exists") throw error;
        workspace = workspacePath(input.root, path);
      }
      return createExperiment(api, { workspace, name: input.name, actions: input.actions, declared_factors: input.factors });
    },
    // A folder may exist even when the registration failed, so refresh either way.
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.experiments() }),
  });
}

export function useRevokeExperiment() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (contextId: string) => revokeExperiment(api, contextId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.experiments() }),
  });
}

export function useIssueCredential() {
  const api = useApi();
  return useMutation({
    gcTime: 0,
    mutationFn: (input: { contextId: string; scopes: BearerScope[]; label: string }) => issueBoundCredential(api, input.contextId, input.scopes, input.label),
  });
}

export function useRegisterPlugin() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: RegisterRequest) => registerPlugin(api, request),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.plugins() }),
  });
}

/** A recheck replaces that plugin's row at once; a later listing replaces it again. */
export function useRecheckPlugin() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => recheckPlugin(api, name),
    onSuccess: (state: PluginState) =>
      queryClient.setQueryData<PluginList>(queryKeys.plugins(), (list) =>
        list === undefined ? list : { ...list, plugins: list.plugins.map((plugin) => (plugin.name === state.name ? state : plugin)) },
      ),
  });
}

export function useUnregisterPlugin() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => unregisterPlugin(api, name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.plugins() }),
  });
}

export function useOpenEditor() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    gcTime: 0,
    mutationFn: (input: { plugin: string; request: OpenRequest }) => openEditor(api, input.plugin, input.request),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.plugins() }),
  });
}

export function useStopEditor() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (launchId: string) => stopEditor(api, launchId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.plugins() }),
  });
}

/** A retry creates a new run, so every run list is stale. */
export function useRetryRun() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => retryRun(api, runId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.allRuns() }),
  });
}
