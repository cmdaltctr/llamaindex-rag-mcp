import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient } from "./client";
import {
  answerCollection,
  changeProfile,
  deleteDocuments,
  getChunk,
  getJob,
  ingestPath,
  isConfirmationRequired,
  isStaleConfirmation,
  joinRootPath,
  listCollections,
  listDocuments,
  listRoots,
  searchCollection,
  uploadFile,
} from "./documents";

interface Sent {
  path: string;
  init: RequestInit;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function recorder(...responses: Response[]) {
  const sent: Sent[] = [];
  const fetchImpl = vi.fn(async (path: string, init?: RequestInit) => {
    sent.push({ path, init: init ?? {} });
    const next = responses.shift();
    if (next === undefined) throw new Error(`Unexpected request to ${path}`);
    return next;
  });
  return { sent, fetchImpl, api: createApiClient(fetchImpl) };
}

function bodyOf(sent: Sent): Record<string, unknown> {
  return JSON.parse(String(sent.init.body)) as Record<string, unknown>;
}

describe("document listing", () => {
  it("lists collections and the sources of one collection", async () => {
    const { sent, api } = recorder(
      json([{ name: "documents", document_count: 2, chunk_count: 9 }]),
      json([{ source: "/a.md", source_id: "s1", chunks: 3, orphaned: null }]),
    );
    expect(await listCollections(api)).toEqual([{ name: "documents", document_count: 2, chunk_count: 9 }]);
    const docs = await listDocuments(api, "my docs");
    expect(docs[0]?.orphaned).toBeNull();
    expect(sent.map((s) => s.path)).toEqual(["/v1/collections", "/v1/collections/my%20docs/documents"]);
  });

  it.each(["", ".", "..", "../x"])("refuses an unsafe collection name %j before fetch", async (name) => {
    const { fetchImpl, api } = recorder();
    await expect(listDocuments(api, name)).rejects.toMatchObject({ kind: "invalid-path" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("lists approved roots", async () => {
    const { api } = recorder(json({ status: "ok", roots: [{ id: "root_a", path: "/srv/docs", kind: "operator" }] }));
    expect(await listRoots(api)).toEqual([{ id: "root_a", path: "/srv/docs", kind: "operator" }]);
  });
});

describe("search and answer", () => {
  it("sends null for every omitted control so the profile decides", async () => {
    const { sent, api } = recorder(json([]));
    await searchCollection(api, "documents", { query: "q" });
    expect(sent[0]?.path).toBe("/v1/collections/documents/search");
    expect(sent[0]?.init.method).toBe("POST");
    expect(bodyOf(sent[0]!)).toEqual({ query: "q", top_k: null, rerank: null, hybrid: null, metadata_filter: null });
  });

  it("passes explicit controls through unchanged", async () => {
    const { sent, api } = recorder(json({ status: "ok" }));
    await answerCollection(api, 
      "documents",
      { query: "q", top_k: 4, rerank: false, hybrid: true, metadata_filter: { lang: "ar" } },
    );
    expect(bodyOf(sent[0]!)).toEqual({ query: "q", top_k: 4, rerank: false, hybrid: true, metadata_filter: { lang: "ar" } });
  });

  it("reads a stored chunk with a neighbour window", async () => {
    const { sent, api } = recorder(json({ status: "ok", previous: [], next: [] }));
    await getChunk(api, "documents", "c:1", 2);
    expect(sent[0]?.path).toBe("/v1/collections/documents/chunks/c%3A1?window=2");
  });
});

describe("preview-bound actions", () => {
  it("previews a deletion, then confirms it with the token", async () => {
    const { sent, api } = recorder(json({ status: "ok", would_delete: 3 }), json({ status: "ok", chunks_removed: 3 }));
    await deleteDocuments(api, "documents", { path: "/a.md" }, { preview: true });
    await deleteDocuments(api, "documents", { path: "/a.md" }, { token: "tok" });
    expect(sent.map((s) => s.init.method)).toEqual(["DELETE", "DELETE"]);
    expect(bodyOf(sent[0]!)).toEqual({ path: "/a.md", dry_run: true });
    expect(bodyOf(sent[1]!)).toEqual({ path: "/a.md", confirmation_token: "tok" });
  });

  it("previews and confirms a profile change", async () => {
    const { sent, api } = recorder(json({ status: "preview" }), json({ status: "ok" }));
    await changeProfile(api, "documents", "codebase", { preview: true });
    await changeProfile(api, "documents", "codebase", { token: "tok" });
    expect(sent[0]?.init.method).toBe("PATCH");
    expect(bodyOf(sent[0]!)).toEqual({ profile: "codebase", confirm: false });
    expect(bodyOf(sent[1]!)).toEqual({ profile: "codebase", confirm: true, confirmation_token: "tok" });
  });

  it("reports a stale preview (409) and a missing token (428) as distinct errors", async () => {
    const { api } = recorder(
      json({ status: "error", message: "The preview is stale. Preview again." }, 409),
      json({ status: "error", message: "Confirmation required." }, 428),
    );
    const stale = await deleteDocuments(api, "documents", {}, { token: "old" }).catch((e: unknown) => e);
    const missing = await deleteDocuments(api, "documents", {}, { token: "" }).catch((e: unknown) => e);
    expect(stale).toBeInstanceOf(ApiError);
    expect((stale as ApiError).message).toBe("The preview is stale. Preview again.");
    expect(isStaleConfirmation(stale)).toBe(true);
    expect(isConfirmationRequired(stale)).toBe(false);
    expect(isConfirmationRequired(missing)).toBe(true);
  });

  it("rejects HTML from a write route instead of parsing it", async () => {
    const html = new Response("<html></html>", { status: 200, headers: { "content-type": "text/html" } });
    const { api } = recorder(html);
    await expect(changeProfile(api, "documents", "documents", { preview: true })).rejects.toMatchObject({
      kind: "not-json",
    });
  });
});

describe("uploads and jobs", () => {
  const file = new File(["hello"], "notes ü.md", { type: "text/markdown" });

  it("preflights, then streams the raw file with an encoded name header", async () => {
    const { sent, api } = recorder(
      json({ status: "ok", name: "notes ü.md", max_bytes: 52428800 }),
      json({ status: "ok", upload: { id: "u1", name: "notes ü.md", size: 5, sha256: "abc" } }, 201),
    );
    const record = await uploadFile(api, file);
    expect(record).toEqual({ id: "u1", name: "notes ü.md", size: 5, sha256: "abc" });
    expect(sent[0]?.path).toBe("/v1/uploads/preflight");
    expect(bodyOf(sent[0]!)).toEqual({ name: "notes ü.md", size: 5 });
    expect(sent[1]?.path).toBe("/v1/uploads");
    const headers = new Headers(sent[1]?.init.headers);
    expect(headers.get("X-Upload-Name")).toBe("notes%20%C3%BC.md");
    expect(headers.get("Content-Type")).toBe("application/octet-stream");
    expect(sent[1]?.init.body).toBe(file);
  });

  it("does not send the bytes when the preflight rejects the file", async () => {
    const { fetchImpl, api } = recorder(json({ status: "error", message: "The file is larger than 50 MiB." }, 413));
    await expect(uploadFile(api, file)).rejects.toMatchObject({
      status: 413,
      message: "The file is larger than 50 MiB.",
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("queues ingestion and polls the job", async () => {
    const job = { job_id: "j1", status: "queued", result: null, error: null, created_at: "t", updated_at: "t" };
    const { sent, api } = recorder(json(job, 202), json({ ...job, status: "completed" }));
    expect((await ingestPath(api, "/srv/docs/a.md", "documents")).status).toBe("queued");
    expect((await getJob(api, "j1")).status).toBe("completed");
    expect(bodyOf(sent[0]!)).toEqual({ path: "/srv/docs/a.md", collection: "documents" });
    expect(sent[1]?.path).toBe("/v1/jobs/j1");
  });
});

describe("joinRootPath", () => {
  it("joins a relative path onto an approved root", () => {
    expect(joinRootPath("/srv/docs/", "reports/a.md")).toBe("/srv/docs/reports/a.md");
    expect(joinRootPath("/srv/docs", "./a.md")).toBe("/srv/docs/a.md");
    expect(joinRootPath("C:\\docs", "sub/a.md")).toBe("C:\\docs\\sub\\a.md");
  });

  it.each(["/etc/passwd", "~/x", "C:\\x", "\\\\server\\share", "../x", "a/../../x", "", "   ", "a\u0000b"])(
    "refuses %j",
    (relative) => {
      expect(() => joinRootPath("/srv/docs", relative)).toThrow();
    },
  );
});
