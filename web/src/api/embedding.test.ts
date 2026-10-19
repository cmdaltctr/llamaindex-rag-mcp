import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient } from "./client";
import { checkEmbeddingModel, embeddingLockOf, embeddingRefusalReason, listEmbeddingProviders, saveProfileEmbedding } from "./embedding";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function fetchReturning(response: Response) {
  return vi.fn(async (input: string, init?: RequestInit) => {
    void input;
    void init;
    return response;
  });
}

const PROFILE = {
  profile_id: "papers-search",
  kind: "user",
  title: "Papers search",
  description: "",
  base_profile: "documents",
  slots: { ingest: "p1", search: "p2", answer: "p3" },
  ready: true,
  not_ready_reasons: [],
  used_by: [],
  embedding: { provider: "ollama", model: "nomic-embed-text", source: "profile", dimensions: 768 },
  embedding_lock: { locked: false, collections: [] },
};

describe("embedding provider client", () => {
  it("lists the providers and the server default", async () => {
    const body = {
      status: "ok",
      providers: [
        { name: "ollama", available: true, reason: null },
        { name: "onnx", available: false, reason: "Not installed." },
      ],
      server_default: { provider: "ollama", model: "nomic-embed-text" },
    };
    const fetchImpl = fetchReturning(json(body));
    const result = await listEmbeddingProviders(createApiClient(fetchImpl));
    expect(result.providers).toHaveLength(2);
    expect(result.server_default).toEqual({ provider: "ollama", model: "nomic-embed-text" });
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/embedding-providers");
  });

  it("checks a model with a POST body and encodes the provider", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", ok: true, dimensions: 768, norm: 1, reason: null }));
    const result = await checkEmbeddingModel(createApiClient(fetchImpl), "a/b", "nomic-embed-text");
    expect(result).toMatchObject({ ok: true, dimensions: 768 });
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/embedding-providers/a%2Fb/check");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ model: "nomic-embed-text" });
  });

  it("returns a failed check as a result, not an error", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", ok: false, dimensions: null, norm: null, reason: "Model not found." }));
    expect(await checkEmbeddingModel(createApiClient(fetchImpl), "ollama", "nope")).toMatchObject({ ok: false, reason: "Model not found." });
  });
});

describe("saveProfileEmbedding", () => {
  it("saves a choice with PUT and returns the profile", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", profile: PROFILE }));
    const profile = await saveProfileEmbedding(createApiClient(fetchImpl), "papers-search", { provider: "ollama", model: "nomic-embed-text" });
    expect(profile.embedding?.model).toBe("nomic-embed-text");
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/profiles/papers-search/embedding");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ provider: "ollama", model: "nomic-embed-text" });
  });

  it("clears the choice with two nulls", async () => {
    const fetchImpl = fetchReturning(json({ status: "ok", profile: PROFILE }));
    await saveProfileEmbedding(createApiClient(fetchImpl), "papers-search", { provider: null, model: null });
    expect(JSON.parse(String(fetchImpl.mock.calls[0]?.[1]?.body))).toEqual({ provider: null, model: null });
  });

  it("keeps the 409 lock body on the error", async () => {
    const body = {
      status: "error",
      message: "Locked.",
      error_type: "embedding_locked",
      collections: [{ collection: "papers", provider: "ollama", model: "nomic-embed-text", chunk_count: 12 }],
    };
    const api = createApiClient(fetchReturning(json(body, 409)));
    const error = await saveProfileEmbedding(api, "papers-search", { provider: "ollama", model: "other" }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(embeddingLockOf(error)).toEqual([{ collection: "papers", provider: "ollama", model: "nomic-embed-text", chunk_count: 12 }]);
    expect(embeddingRefusalReason(error)).toBeNull();
  });

  it("reads the reason of a 422 failed check", async () => {
    const body = { status: "error", message: "Check failed.", reason: "Model not found." };
    const api = createApiClient(fetchReturning(json(body, 422)));
    const error = await saveProfileEmbedding(api, "papers-search", { provider: "ollama", model: "nope" }).catch((caught: unknown) => caught);
    expect(embeddingRefusalReason(error)).toBe("Model not found.");
    expect(embeddingLockOf(error)).toBeNull();
  });

  it("returns no lock and no reason for an unrelated failure", () => {
    expect(embeddingLockOf(new Error("x"))).toBeNull();
    expect(embeddingRefusalReason(new ApiError("http", "x", "/v1/x", 500, { status: "error" }))).toBeNull();
  });
});
