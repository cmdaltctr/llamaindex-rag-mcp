import { vi } from "vitest";
import type { FetchLike } from "../../api/client";
import { ACTIVE_RUN, FAILED_EVENTS, FAILED_RESULT, FAILED_RUN } from "../../experiments/test/runFixtures";
import { runRouter, type RunRouterOptions } from "../../experiments/test/runRouter";

/** In-memory stand-in for the run and chunk routes alone. Records every request. */
export function runServer(options: Partial<RunRouterOptions> = {}) {
  const router = runRouter({ runs: [FAILED_RUN, ACTIVE_RUN], results: { r1: FAILED_RESULT }, events: { r1: FAILED_EVENTS }, ...options });
  const calls: { method: string; path: string }[] = [];
  const fetchImpl = vi.fn<FetchLike>(async (path, init) => {
    const method = init?.method ?? "GET";
    calls.push({ method, path });
    return router.route(method, new URL(path, "http://omrg.test"));
  });
  return { fetchImpl, calls, runs: router.runs };
}
