import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render, renderHook, type RenderHookOptions, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { ApiProvider } from "../api/ApiProvider";
import type { FetchLike } from "../api/client";
import { createQueryClient } from "../api/queries";

interface ProviderOptions {
  /** A fixture server's fetch. The client is built from it once. */
  fetchImpl?: FetchLike;
  /** Pass one to inspect the cache; every test otherwise gets a fresh client with `retry: false`. */
  queryClient?: QueryClient;
}

/** Wraps children in the providers the app root supplies, with a fresh `QueryClient` by default. */
export function providers({ fetchImpl, queryClient = createQueryClient({ retry: false }) }: ProviderOptions = {}) {
  return function Providers({ children }: { children: ReactNode }) {
    return (
      <ApiProvider fetchImpl={fetchImpl}>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </ApiProvider>
    );
  };
}

export function renderWithProviders(ui: ReactElement, options: ProviderOptions & Omit<RenderOptions, "wrapper"> = {}) {
  const { fetchImpl, queryClient, ...rest } = options;
  return render(ui, { wrapper: providers({ fetchImpl, queryClient }), ...rest });
}

export function renderHookWithProviders<Result>(hook: () => Result, options: ProviderOptions & Omit<RenderHookOptions<unknown>, "wrapper"> = {}) {
  const { fetchImpl, queryClient, ...rest } = options;
  return renderHook(hook, { wrapper: providers({ fetchImpl, queryClient }), ...rest });
}
