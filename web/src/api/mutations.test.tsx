import { useQuery } from "@tanstack/react-query";
import { act, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { renderHookWithProviders } from "../test/providers";
import { useApi } from "./ApiProvider";
import { useAnswer, useChangeProfile, useCreatePipeline, useDeleteDocuments, useIngestPath, useSaveRevision, useSearch, useUploadFile } from "./mutations";
import { collectionsQuery, documentsQuery, pipelinesQuery } from "./queries";

const JOB = { job_id: "j1", result: null, error: null, created_at: "", updated_at: "" };
const PREVIEW = { status: "preview", contract: { collection: "documents", new_profile: "codebase", old_profile: "documents", chunk_count: 12, lever_impacts: [], reingest_pointer: "" }, confirm_required: true };

function collectionReads(server: ReturnType<typeof documentsServer>) {
  return server.find("GET", "/v1/collections").filter((call) => call.path === "/v1/collections").length;
}

/** Mounts the collection and document reads beside the hook under test, so invalidation is observable. */
function mount<T>(server: ReturnType<typeof documentsServer>, hook: () => T) {
  return renderHookWithProviders(
    () => {
      const api = useApi();
      return { collections: useQuery(collectionsQuery(api)), documents: useQuery(documentsQuery(api, "documents")), hook: hook() };
    },
    { fetchImpl: server.fetchImpl },
  );
}

describe("mutations that change what the collection list shows", () => {
  it("refreshes the collections after an upload", async () => {
    const server = documentsServer({
      "POST /v1/uploads/preflight": () => ({ status: "ok" }),
      "POST /v1/uploads": () => ({ upload: { id: "u1", name: "a.md", size: 1, sha256: "x" } }),
    });
    const { result } = mount(server, useUploadFile);
    await waitFor(() => expect(result.current.collections.isSuccess).toBe(true));
    await act(() => result.current.hook.mutateAsync(new File(["a"], "a.md")));
    await waitFor(() => expect(collectionReads(server)).toBe(2));
  });

  it("refreshes the collections and the documents after a confirmed deletion", async () => {
    const server = documentsServer({ "DELETE /v1/collections/documents/documents": () => ({ status: "ok", mode: "path", collection: "documents", chunks_removed: 5 }) });
    const { result } = mount(server, () => useDeleteDocuments("documents"));
    await waitFor(() => expect(result.current.documents.isSuccess).toBe(true));
    await act(() => result.current.hook.mutateAsync({ selector: { path: "/srv/docs/gone.md" }, step: { token: "t" } }));
    await waitFor(() => expect(collectionReads(server)).toBe(2));
    await waitFor(() => expect(server.find("GET", "/v1/collections/documents/documents")).toHaveLength(2));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(server.find("GET", "/v1/collections/documents/documents")).toHaveLength(2);
  });

  it("does not refresh anything for a deletion preview", async () => {
    const server = documentsServer({
      "DELETE /v1/collections/documents/documents": () => ({ status: "ok", mode: "path", collection: "documents", dry_run: true, would_delete: 5 }),
    });
    const { result } = mount(server, () => useDeleteDocuments("documents"));
    await waitFor(() => expect(result.current.collections.isSuccess).toBe(true));
    await act(() => result.current.hook.mutateAsync({ selector: { path: "/srv/docs/gone.md" }, step: { preview: true } }));
    expect(collectionReads(server)).toBe(1);
  });

  it("refreshes the collections after a confirmed profile change, not after its preview", async () => {
    const server = documentsServer({
      "PATCH /v1/collections/documents/profile": (body) =>
        body.confirm === true ? { status: "ok", collection: "documents", profile: "codebase", chunk_count_unchanged: 12 } : PREVIEW,
    });
    const { result } = mount(server, () => useChangeProfile("documents"));
    await waitFor(() => expect(result.current.collections.isSuccess).toBe(true));
    await act(() => result.current.hook.mutateAsync({ profile: "codebase", step: { preview: true } }));
    expect(collectionReads(server)).toBe(1);
    await act(() => result.current.hook.mutateAsync({ profile: "codebase", step: { token: "t" } }));
    await waitFor(() => expect(collectionReads(server)).toBe(2));
  });

  it("refreshes the collections when a started ingest job finishes, with no view following it", async () => {
    let status = "running";
    const server = documentsServer({
      "POST /v1/ingestions": () => json({ ...JOB, job_id: "j1", status: "queued" }, 202),
      "GET /v1/jobs/j1": () => ({ ...JOB, job_id: "j1", status }),
    });
    const { result } = renderHookWithProviders(
      () => {
        const api = useApi();
        return { collections: useQuery(collectionsQuery(api)), ingest: useIngestPath() };
      },
      { fetchImpl: server.fetchImpl },
    );
    await waitFor(() => expect(result.current.collections.isSuccess).toBe(true));
    await act(() => result.current.ingest.mutateAsync({ path: "/srv/a.md", collection: "documents" }));
    await waitFor(() => expect(server.find("GET", "/v1/jobs/j1").length).toBeGreaterThan(0));
    expect(collectionReads(server)).toBe(1);
    status = "completed";
    await waitFor(() => expect(collectionReads(server)).toBe(2), { timeout: 4000 });
  });

  it("refreshes the collections once for a failed job as well", async () => {
    const server = documentsServer({
      "POST /v1/ingestions": () => json({ ...JOB, job_id: "j2", status: "queued" }, 202),
      "GET /v1/jobs/j2": () => ({ ...JOB, job_id: "j2", status: "failed", error: "x" }),
    });
    const { result } = renderHookWithProviders(
      () => {
        const api = useApi();
        return { collections: useQuery(collectionsQuery(api)), ingest: useIngestPath() };
      },
      { fetchImpl: server.fetchImpl },
    );
    await waitFor(() => expect(result.current.collections.isSuccess).toBe(true));
    await act(() => result.current.ingest.mutateAsync({ path: "/srv/a.md", collection: "documents" }));
    await waitFor(() => expect(collectionReads(server)).toBe(2), { timeout: 4000 });
  });

  it("refreshes the collections when the job cannot be read any more", async () => {
    const server = documentsServer({
      "POST /v1/ingestions": () => json({ ...JOB, job_id: "j3", status: "queued" }, 202),
      "GET /v1/jobs/j3": () => json({ status: "error", message: "gone" }, 404),
    });
    const { result } = renderHookWithProviders(
      () => {
        const api = useApi();
        return { collections: useQuery(collectionsQuery(api)), ingest: useIngestPath() };
      },
      { fetchImpl: server.fetchImpl },
    );
    await waitFor(() => expect(result.current.collections.isSuccess).toBe(true));
    await act(() => result.current.ingest.mutateAsync({ path: "/srv/a.md", collection: "documents" }));
    await waitFor(() => expect(collectionReads(server)).toBe(2), { timeout: 4000 });
  });
});

describe("mutations for pipelines", () => {
  it("refreshes the pipeline list after a revision is saved", async () => {
    const server = documentsServer({
      "GET /v1/pipelines": () => ({ pipelines: [] }),
      "POST /v1/pipelines/p1/revisions": () => ({ revision: { revision_id: "r1" }, created: true }),
    });
    const { result } = renderHookWithProviders(
      () => {
        const api = useApi();
        return { list: useQuery(pipelinesQuery(api)), save: useSaveRevision("p1") };
      },
      { fetchImpl: server.fetchImpl },
    );
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));
    await act(() => result.current.save.mutateAsync({ schema_version: 1, nodes: [], edges: [], inputs: [], outputs: [] } as never));
    await waitFor(() => expect(server.find("GET", "/v1/pipelines").filter((c) => c.path === "/v1/pipelines")).toHaveLength(2));
  });

  it("refreshes the pipeline list after a pipeline is created", async () => {
    const server = documentsServer({
      "GET /v1/pipelines": () => ({ pipelines: [] }),
      "POST /v1/pipelines": () => ({ pipeline: { pipeline_id: "p9", title: "T" } }),
    });
    const { result } = renderHookWithProviders(
      () => {
        const api = useApi();
        return { list: useQuery(pipelinesQuery(api)), create: useCreatePipeline() };
      },
      { fetchImpl: server.fetchImpl },
    );
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));
    await act(() => result.current.create.mutateAsync({ title: "T", layout: { title: "T", positions: {} } }));
    await waitFor(() => expect(server.find("GET", "/v1/pipelines").filter((c) => c.path === "/v1/pipelines")).toHaveLength(2));
  });
});

describe("answers and searches", () => {
  it("send a fresh request each time and invalidate nothing", async () => {
    const server = documentsServer({
      "POST /v1/collections/documents/answer": () => ({ status: "ok", query: "q", answer: "a", citations: [], evidence: [], failure_stage: null, error: null, completion_source: "server" }),
      "POST /v1/collections/documents/search": () => [],
    });
    const { result } = mount(server, () => ({ answer: useAnswer("documents"), search: useSearch("documents") }));
    await waitFor(() => expect(result.current.collections.isSuccess).toBe(true));
    await act(() => result.current.hook.answer.mutateAsync({ query: "q" }));
    await act(() => result.current.hook.answer.mutateAsync({ query: "q" }));
    await act(() => result.current.hook.search.mutateAsync({ query: "q" }));
    expect(server.find("POST", "/v1/collections/documents/answer")).toHaveLength(2);
    expect(server.find("POST", "/v1/collections/documents/search")).toHaveLength(1);
    expect(collectionReads(server)).toBe(1);
  });
});
