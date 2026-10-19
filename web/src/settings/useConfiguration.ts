import { queryOptions, useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import type { ApiClient } from "../api/client";
import type { ConfigurationState } from "./configurationTypes";

/** Every setting with its value in force and source. Read-only; sends no request to any provider. */
export const configurationQuery = (api: ApiClient) =>
  queryOptions({
    queryKey: ["settings", "configuration"] as const,
    queryFn: ({ signal }) => api.request<ConfigurationState>("GET", "/v1/settings/configuration", { signal }),
  });

export function useConfiguration() {
  return useQuery(configurationQuery(useApi()));
}
