/**
 * The stamp of `omrg.jsonc` that the page saw last (design D5). Every Settings
 * read and every Settings write returns it, and every write sends it back, so a
 * file changed on disk since the page read it gives 409 and the page asks for a
 * reload. All Settings routes share one file, so one stamp serves them all.
 */
import type { QueryClient } from "@tanstack/react-query";

const KEY = ["settings-revision"] as const;
/** The key of `GET /v1/settings/configuration` (`settings/useConfiguration.ts`). */
const CONFIGURATION_KEY = ["settings", "configuration"] as const;

/** Query keys (first element) whose data comes from `omrg.jsonc`. */
const SETTINGS_ROOTS: readonly unknown[] = ["settings", "connections", "mcp", "llamacpp-server"];

export function currentRevision(queryClient: QueryClient): string | undefined {
  return queryClient.getQueryData<string>(KEY);
}

/** Keeps the `revision` of a response; a response without one changes nothing. Returns the response. */
export function rememberRevision<T>(queryClient: QueryClient, response: T): T {
  const revision = (response as { revision?: unknown } | null)?.revision;
  if (typeof revision === "string") queryClient.setQueryData(KEY, revision);
  return response;
}

/**
 * Call with the response of every Settings write: keeps its revision and marks
 * the Configuration listing stale, because that listing shows the file too.
 */
export function settingsWritten<T>(queryClient: QueryClient, response: T): T {
  void queryClient.invalidateQueries({ queryKey: CONFIGURATION_KEY });
  return rememberRevision(queryClient, response);
}

/** Reads every Settings route again, so the page shows the file as it is now and holds its new revision. */
export function reloadSettings(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries({ predicate: (query) => SETTINGS_ROOTS.includes(query.queryKey[0]) });
}
