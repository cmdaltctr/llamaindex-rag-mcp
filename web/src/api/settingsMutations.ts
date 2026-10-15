/**
 * Settings writes. Each one puts the state the server returned into the
 * cache, or invalidates the key it changed, so the page shows what the server
 * holds and never an assumed state.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useApi } from "./ApiProvider";
import { queryKeys } from "./queries";
import { revokeMcpToken, rotateMcpToken, setMcpEnabled, setUploadLimit, setWebPort } from "./settings";

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
