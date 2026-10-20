/**
 * Settings writes. Each one puts the state the server returned into the
 * cache, or invalidates the key it changed, so the page shows what the server
 * holds and never an assumed state.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useApi } from "./ApiProvider";
import { queryKeys } from "./queries";
import { currentRevision, settingsWritten } from "./settingsRevision";
import {
  removeProviderKey,
  revokeMcpToken,
  rotateMcpToken,
  saveProviderFields,
  saveProviderKey,
  setChatSettings,
  setMcpEnabled,
  setUploadLimit,
  setWebPort,
  type ChatChoice,
} from "./settings";
import { saveDocumentReadingSettings, type DocumentReadingValues } from "./settingsDocumentReading";

/**
 * The options every Settings write sends (the revision last seen) and what it
 * does with the response (keeps the new revision). Read at call time, so a write
 * sent right after another uses the revision the first one returned.
 */
function useRevision() {
  const queryClient = useQueryClient();
  return {
    options: () => ({ revision: currentRevision(queryClient) }),
    remember: <T,>(response: T) => settingsWritten(queryClient, response),
  };
}

export function useSetMcpEnabled() {
  const api = useApi();
  const queryClient = useQueryClient();
  const { options, remember } = useRevision();
  return useMutation({
    mutationFn: (enabled: boolean) => setMcpEnabled(api, enabled, options()),
    onSuccess: (state) => queryClient.setQueryData(queryKeys.mcp(), remember(state)),
  });
}

/** Creates the token or replaces it. The caller keeps the returned value; the cache never holds it. */
export function useRotateMcpToken() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => rotateMcpToken(api),
    gcTime: 0,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.mcp() }),
  });
}

export function useRevokeMcpToken() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => revokeMcpToken(api),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.mcp() }),
  });
}

export function useSetWebPort() {
  const api = useApi();
  const queryClient = useQueryClient();
  const { options, remember } = useRevision();
  return useMutation({
    mutationFn: (port: number | null) => setWebPort(api, port, options()),
    onSuccess: (state) => queryClient.setQueryData(queryKeys.webPort(), remember(state)),
  });
}

/** Invalidates `["settings", "upload-limit"]`, so the Knowledge Base upload panel reads the new limit too. */
export function useSetUploadLimit() {
  const api = useApi();
  const queryClient = useQueryClient();
  const { options, remember } = useRevision();
  return useMutation({
    mutationFn: (maxMib: number | null) => setUploadLimit(api, maxMib, options()),
    onSuccess: (state) => {
      remember(state);
      return queryClient.invalidateQueries({ queryKey: queryKeys.uploadLimit() });
    },
  });
}

/** A provider write changes the cards and can change whether Chat is ready, so both reads refresh. */
function useRefreshProviders() {
  const queryClient = useQueryClient();
  const { remember } = useRevision();
  return (response: unknown) => {
    remember(response);
    return Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.connections() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.chatSettings() }),
    ]);
  };
}

/** Saves addresses (a `null` clears one). The card shows what the server holds after the refresh. */
export function useSaveProviderFields(provider: string) {
  const api = useApi();
  const refresh = useRefreshProviders();
  const { options } = useRevision();
  return useMutation({
    mutationFn: (fields: Record<string, string | number | null>) => saveProviderFields(api, provider, fields, options()),
    onSuccess: refresh,
  });
}

/** Saves a key. The variables of the mutation hold the key, so the cache is dropped at once (`gcTime: 0`). */
export function useSaveProviderKey(provider: string) {
  const api = useApi();
  const refresh = useRefreshProviders();
  const { options } = useRevision();
  return useMutation({
    mutationFn: (apiKey: string) => saveProviderKey(api, provider, apiKey, options()),
    gcTime: 0,
    onSuccess: refresh,
  });
}

export function useRemoveProviderKey(provider: string) {
  const api = useApi();
  const refresh = useRefreshProviders();
  const { options } = useRevision();
  return useMutation({ mutationFn: () => removeProviderKey(api, provider, options()), onSuccess: refresh });
}

/** Saves the Chat choice, or clears it with `null`. */
export function useSetChatSettings() {
  const api = useApi();
  const queryClient = useQueryClient();
  const { options, remember } = useRevision();
  return useMutation({
    mutationFn: (choice: ChatChoice | null) => setChatSettings(api, choice, options()),
    onSuccess: (response) => {
      remember(response);
      return queryClient.invalidateQueries({ queryKey: queryKeys.chatSettings() });
    },
  });
}

/** Saves document reading keys for the next launch (`null` resets one). The section shows the state the server returned. */
export function useSaveDocumentReading() {
  const api = useApi();
  const queryClient = useQueryClient();
  const { options, remember } = useRevision();
  return useMutation({
    mutationFn: (values: DocumentReadingValues) => saveDocumentReadingSettings(api, values, options()),
    onSuccess: (state) => queryClient.setQueryData(queryKeys.documentReading(), remember(state)),
  });
}
