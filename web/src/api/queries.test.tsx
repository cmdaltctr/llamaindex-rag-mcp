import { useQuery } from "@tanstack/react-query";
import { waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { renderHookWithProviders } from "../test/providers";
import { useApi } from "./ApiProvider";
import { ApiError, createApiClient, type FetchLike } from "./client";
import { collectionsQuery, createQueryClient, jobQuery, queryKeys, runsQuery, shouldRetry } from "./queries";

describe("query keys", () => {
  it("nest under their collection so one prefix invalidates the group", () => {
    expect(queryKeys.collections()).toEqual(["collections"]);
    expect(queryKeys.documents("papers")).toEqual(["collections", "papers", "documents"]);
    expect(queryKeys.run("r1")).toEqual(["runs", "r1"]);
    expect(queryKeys.runs({ limit: 1 })).toEqual(["runs", { limit: 1 }]);
    expect(queryKeys.pipeline("p1")).toEqual(["pipelines", "p1"]);
    expect(queryKeys.runArtefact("r1", "event-1")).toEqual(["runs", "r1", "artefacts", "event-1"]);
  });
});

describe("query client defaults", () => {
  const network = new ApiError("network", "x", "/v1/x");
  const http = new ApiError("http", "x", "/v1/x", 500);

  it("retries a network error once and nothing else", () => {
    expect(shouldRetry(0, network)).toBe(true);
    expect(shouldRetry(1, network)).toBe(false);
    expect(shouldRetry(0, http)).toBe(false);
    expect(shouldRetry(0, new ApiError("not-json", "x", "/v1/x", 200))).toBe(false);
    expect(shouldRetry(0, new Error("x"))).toBe(false);
  });

  it("turns focus refetching off and keeps reads fresh for a while", () => {
    const options = createQueryClient().getDefaultOptions();
    expect(options.queries?.refetchOnWindowFocus).toBe(false);
    expect(options.queries?.staleTime).toBeGreaterThan(0);
    expect(options.queries?.retry).toBe(shouldRetry);
  });

  it("lets a test turn retry off and nothing else", () => {
    const options = createQueryClient({ retry: false }).getDefaultOptions();
    expect(options.queries?.retry).toBe(false);
    expect(options.queries?.staleTime).toBe(createQueryClient().getDefaultOptions().queries?.staleTime);
  });

  it("does not retry a failing http read in the app client", async () => {
    const fetchImpl = vi.fn<FetchLike>(async () => json({ message: "boom" }, 500));
    const queryClient = createQueryClient();
    const { result } = renderHookWithProviders(() => useQuery(collectionsQuery(useApi())), { fetchImpl, queryClient });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(result.current.error).toBeInstanceOf(ApiError);
  });
});

describe("shared reads", () => {
  it("requests the collection list once for two consumers", async () => {
    const server = documentsServer();
    const { result } = renderHookWithProviders(
      () => {
        const api = useApi();
        return { home: useQuery(collectionsQuery(api)), chat: useQuery(collectionsQuery(api)) };
      },
      { fetchImpl: server.fetchImpl },
    );
    await waitFor(() => expect(result.current.chat.isSuccess).toBe(true));
    expect(result.current.home.data).toEqual(result.current.chat.data);
    expect(server.find("GET", "/v1/collections")).toHaveLength(1);
  });

  it("filters runs by the options it is given", async () => {
    const server = documentsServer({ "GET /v1/runs": () => ({ status: "ok", runs: [] }) });
    const { result } = renderHookWithProviders(() => useQuery(runsQuery(useApi(), { pipelineId: "pl_1", limit: 1 })), { fetchImpl: server.fetchImpl });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(server.calls[0]?.path).toBe("/v1/runs?limit=1&pipeline_id=pl_1");
  });
});

describe("job polling", () => {
  it("keeps polling while a job runs and stops when it completes", async () => {
    const statuses = ["queued", "running", "completed"];
    let index = 0;
    const server = documentsServer({
      "GET /v1/jobs/j1": () => ({ job_id: "j1", status: statuses[Math.min(index++, 2)], result: null, error: null, created_at: "", updated_at: "" }),
    });
    const api = createApiClient(server.fetchImpl);
    expect(jobQuery(api, "j1").queryKey).toEqual(["jobs", "j1"]);
    const interval = jobQuery(api, "j1").refetchInterval as (query: { state: { data?: { status: string } } }) => number | false;
    expect(interval({ state: { data: { status: "running" } } })).toBeGreaterThan(0);
    expect(interval({ state: { data: undefined } })).toBeGreaterThan(0);
    expect(interval({ state: { data: { status: "completed" } } })).toBe(false);
    expect(interval({ state: { data: { status: "failed" } } })).toBe(false);
  });
});
