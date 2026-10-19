import { createContext, useContext, useMemo, type ReactNode } from "react";
import { createApiClient, type ApiClient, type FetchLike } from "./client";

const ApiContext = createContext<ApiClient | null>(null);

interface ApiProviderProps {
  /** Set once at the root. Tests pass a fixture server's fetch here; components never receive it. */
  fetchImpl?: FetchLike;
  children: ReactNode;
}

export function ApiProvider({ fetchImpl, children }: ApiProviderProps) {
  const client = useMemo(() => createApiClient(fetchImpl), [fetchImpl]);
  return <ApiContext.Provider value={client}>{children}</ApiContext.Provider>;
}

/** The API client for the current tree. */
export function useApi(): ApiClient {
  const client = useContext(ApiContext);
  if (client === null) throw new Error("useApi must be used inside an ApiProvider.");
  return client;
}
