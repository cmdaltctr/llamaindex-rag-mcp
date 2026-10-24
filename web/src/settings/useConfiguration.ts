import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import type { ApiClient } from "../api/client";
import { otherSettingsStale, rememberRevision } from "../api/settingsRevision";
import type { ConfigurationChanges, ConfigurationState } from "./configurationTypes";

/** Every setting with its value in force and source. Read-only; sends no request to any provider. */
export const configurationQuery = (api: ApiClient) =>
  queryOptions({
    queryKey: ["settings", "configuration"] as const,
    queryFn: ({ signal }) => api.request<ConfigurationState>("GET", "/v1/settings/configuration", { signal }),
  });

export function useConfiguration() {
  return useQuery(configurationQuery(useApi()));
}

/** Writes all `changes` or none. A stale `revision` gives 409 and writes nothing. */
export function saveConfiguration(api: ApiClient, revision: string, changes: ConfigurationChanges): Promise<ConfigurationState> {
  return api.request<ConfigurationState>("PUT", "/v1/settings/configuration", { body: { revision, changes } });
}

/**
 * Saves Configuration rows with the revision the section read. The response
 * holds the whole listing, so it replaces the cached one and the page shows
 * what the server holds now. The other Settings reads are marked stale.
 */
export function useSaveConfiguration() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ revision, changes }: { revision: string; changes: ConfigurationChanges }) => saveConfiguration(api, revision, changes),
    onSuccess: (state) => {
      queryClient.setQueryData(configurationQuery(api).queryKey, rememberRevision(queryClient, state));
      void otherSettingsStale(queryClient);
    },
  });
}
