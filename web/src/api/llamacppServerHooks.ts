/**
 * The llama.cpp server state and its writes. Every write puts the status the
 * server returned into the cache, so the page shows what the server holds.
 */
import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "./ApiProvider";
import type { ApiClient } from "./client";
import {
  getLlamacppServer,
  restartLlamacppServer,
  saveLlamacppServer,
  startLlamacppServer,
  stopLlamacppServer,
  type LlamacppServerChange,
  type LlamacppServerStatus,
} from "./llamacppServer";

export const llamacppServerKey = ["llamacpp-server"] as const;

/** Milliseconds between reads while the server starts. */
export const STARTING_POLL_MS = 1000;

export const llamacppServerQuery = (api: ApiClient) =>
  queryOptions({
    queryKey: llamacppServerKey,
    queryFn: ({ signal }) => getLlamacppServer(api, { signal }),
    // Poll only while the server starts: the state moves to running or failed on its own.
    refetchInterval: (query) => (query.state.data?.state === "starting" ? STARTING_POLL_MS : false),
  });

export function useLlamacppServer() {
  return useQuery(llamacppServerQuery(useApi()));
}

function useStatusMutation<V>(call: (api: ApiClient, variables: V) => Promise<LlamacppServerStatus>) {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: V) => call(api, variables),
    onSuccess: (status) => queryClient.setQueryData(llamacppServerKey, status),
  });
}

export const useSaveLlamacppServer = () => useStatusMutation<LlamacppServerChange>((api, change) => saveLlamacppServer(api, change));
export const useStartLlamacppServer = () => useStatusMutation<void>((api) => startLlamacppServer(api));
export const useStopLlamacppServer = () => useStatusMutation<void>((api) => stopLlamacppServer(api));
export const useRestartLlamacppServer = () => useStatusMutation<void>((api) => restartLlamacppServer(api));
