import { useQuery } from "@tanstack/react-query";
import { act, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { documentsServer } from "../test/fakeDocumentsServer";
import { renderHookWithProviders } from "../test/providers";
import { useApi } from "./ApiProvider";
import { useCancelRun, useSaveLayout, useSubmitRun, useValidatePipeline } from "./mutations";
import { pipelineQuery, revisionQuery, runsQuery } from "./queries";

const DOC = { schema_version: 1, nodes: [{ id: "dense", operation: "retrieve.dense" }] };

function reads(server: ReturnType<typeof documentsServer>, path: string) {
  return server.find("GET", path).filter((call) => call.path === path).length;
}

describe("mutations for layouts, validation and runs", () => {
  it("refreshes an open pipeline after a layout save", async () => {
    const server = documentsServer({
      "GET /v1/pipelines/p1": () => ({ pipeline: { pipeline_id: "p1" }, current_revision: null }),
      "PUT /v1/pipelines/p1/layout": () => ({ pipeline: { pipeline_id: "p1" } }),
    });
    const { result } = renderHookWithProviders(
      () => ({ list: useQuery(pipelineQuery(useApi(), "p1")), save: useSaveLayout("p1") }),
      { fetchImpl: server.fetchImpl },
    );
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));
    await act(() => result.current.save.mutateAsync({ title: "T" }));
    await waitFor(() => expect(reads(server, "/v1/pipelines/p1")).toBe(2));
  });

  it("checks a draft without refreshing anything", async () => {
    const server = documentsServer({
      "GET /v1/pipelines/p1": () => ({ pipeline: { pipeline_id: "p1" }, current_revision: null }),
      "POST /v1/pipelines/validate": () => ({ valid: true, admitted: false, order: ["dense"] }),
    });
    const { result } = renderHookWithProviders(
      () => ({ list: useQuery(pipelineQuery(useApi(), "p1")), check: useValidatePipeline() }),
      { fetchImpl: server.fetchImpl },
    );
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));
    const report = await act(() => result.current.check.mutateAsync({ document: DOC }));
    expect(report.order).toEqual(["dense"]);
    expect(server.find("POST", "/v1/pipelines/validate")[0]?.body).toEqual({ document: DOC });
    expect(reads(server, "/v1/pipelines/p1")).toBe(1);
  });

  it("refreshes the run lists after a run is submitted and after it is cancelled", async () => {
    const server = documentsServer({
      "GET /v1/runs": () => ({ runs: [] }),
      "POST /v1/runs": () => ({ run: { run_id: "run1", status: "queued" } }),
      "POST /v1/runs/run1/cancel": () => ({ run: { run_id: "run1", status: "cancelling" } }),
    });
    const { result } = renderHookWithProviders(
      () => ({ list: useQuery(runsQuery(useApi(), { pipelineId: "p1", limit: 1 })), submit: useSubmitRun(), cancel: useCancelRun() }),
      { fetchImpl: server.fetchImpl },
    );
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));
    const listReads = () => server.calls.filter((call) => call.path.startsWith("/v1/runs?")).length;
    expect(listReads()).toBe(1);
    await act(() => result.current.submit.mutateAsync({ revisionId: "r1", inputs: { query: "q" } }));
    expect(server.find("POST", "/v1/runs")[0]?.body).toEqual({ revision_id: "r1", inputs: { query: "q" } });
    await waitFor(() => expect(listReads()).toBe(2));
    await act(() => result.current.cancel.mutateAsync("run1"));
    await waitFor(() => expect(listReads()).toBe(3));
  });

  it("reads a revision once and keeps it", async () => {
    const server = documentsServer({ "GET /v1/pipelines/p1/revisions/r1": () => ({ revision: { revision_id: "r1", revision_number: 1 } }) });
    const { result } = renderHookWithProviders(() => useQuery(revisionQuery(useApi(), "p1", "r1")), { fetchImpl: server.fetchImpl });
    await waitFor(() => expect(result.current.data?.revision_number).toBe(1));
    expect(result.current.isStale).toBe(false);
  });
});
