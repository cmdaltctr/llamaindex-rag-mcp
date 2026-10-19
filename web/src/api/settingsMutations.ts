/**
 * Settings writes. Each one puts the state the server returned into the
 * cache, or invalidates the key it changed, so the page shows what the server
 * holds and never an assumed state.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useApi } from "./ApiProvider";
import { queryKeys } from "./queries";
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

export function useSetMcpEnabled() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => setMcpEnabled(api, enabled),
    onSuccess: (state) => queryClient.setQueryData(queryKeys.mcp(), state),
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
  return useMutation({
    mutationFn: (port: number | null) => setWebPort(api, port),
    onSuccess: (state) => queryClient.setQueryData(queryKeys.webPort(), state),
  });
}

/** Invalidates `["settings", "upload-limit"]`, so the Knowledge Base upload panel reads the new limit too. */
export function useSetUploadLimit() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (maxMib: number | null) => setUploadLimit(api, maxMib),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.uploadLimit() }),
  });
}

/** A provider write changes the cards and can change whether Chat is ready, so both reads refresh. */
function useRefreshProviders() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.connections() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.chatSettings() }),
    ]);
}

/** Saves addresses (a `null` clears one). The card shows what the server holds after the refresh. */
export function useSaveProviderFields(provider: string) {
  const api = useApi();
  const refresh = useRefreshProviders();
  return useMutation({
    mutationFn: (fields: Record<string, string | number | null>) => saveProviderFields(api, provider, fields),
    onSuccess: refresh,
  });
}

/** Saves a key. The variables of the mutation hold the key, so the cache is dropped at once (`gcTime: 0`). */
export function useSaveProviderKey(provider: string) {
  const api = useApi();
  const refresh = useRefreshProviders();
  return useMutation({
    mutationFn: (apiKey: string) => saveProviderKey(api, provider, apiKey),
    gcTime: 0,
    onSuccess: refresh,
  });
}

export function useRemoveProviderKey(provider: string) {
  const api = useApi();
  const refresh = useRefreshProviders();
  return useMutation({ mutationFn: () => removeProviderKey(api, provider), onSuccess: refresh });
}

/** Saves the Chat choice, or clears it with `null`. */
export function useSetChatSettings() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (choice: ChatChoice | null) => setChatSettings(api, choice),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.chatSettings() }),
  });
}
