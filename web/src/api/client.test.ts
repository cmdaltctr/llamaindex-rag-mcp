import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient, type ApiErrorKind, type FetchLike } from "./client";

function respond(body: string, init: { status?: number; type?: string }) {
  const headers: Record<string, string> = init.type === undefined ? {} : { "content-type": init.type };
  return vi.fn<FetchLike>(async () => new Response(body, { status: init.status ?? 200, headers }));
}

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    return error as ApiError;
  }
  throw new Error("expected the request to fail");
}

describe("api client", () => {
  it("returns parsed JSON for a JSON response", async () => {
    const fetchImpl = respond('{"status":"ok"}', { type: "application/json; charset=utf-8" });
    const api = createApiClient(fetchImpl);
    await expect(api.request("GET", "/v1/health")).resolves.toEqual({ status: "ok" });
    expect(fetchImpl).toHaveBeenCalledWith(
      "/v1/health",
      expect.objectContaining({
        method: "GET",
        credentials: "same-origin",
        headers: expect.objectContaining({ Accept: "application/json" }),
      }),
    );
  });

  it("appends query values and skips null and undefined", async () => {
    const fetchImpl = respond("[]", { type: "application/json" });
    const api = createApiClient(fetchImpl);
    await api.request("GET", "/v1/runs", { query: { pipeline_id: "p 1", limit: 1, status: undefined, after: null, live: false } });
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/v1/runs?pipeline_id=p+1&limit=1&live=false");
  });

  it("sends a JSON body with a content type", async () => {
    const fetchImpl = respond("{}", { type: "application/json" });
    const api = createApiClient(fetchImpl);
    await api.request("POST", "/v1/pipelines", { body: { title: "x" } });
    const init = fetchImpl.mock.calls[0]?.[1];
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe('{"title":"x"}');
    expect(init?.headers).toMatchObject({ "Content-Type": "application/json" });
  });

  it("sends no body and no content type when none is given", async () => {
    const fetchImpl = respond("{}", { type: "application/json" });
    const api = createApiClient(fetchImpl);
    await api.request("DELETE", "/v1/plugins/a");
    const init = fetchImpl.mock.calls[0]?.[1];
    expect(init?.body).toBeUndefined();
    expect(init?.headers).not.toHaveProperty("Content-Type");
  });

  it("sends a Blob as the raw body with the caller headers", async () => {
    const fetchImpl = respond("{}", { type: "application/json" });
    const api = createApiClient(fetchImpl);
    const file = new File(["abc"], "a.txt");
    await api.request("POST", "/v1/uploads", { body: file, headers: { "Content-Type": "application/octet-stream" } });
    const init = fetchImpl.mock.calls[0]?.[1];
    expect(init?.body).toBe(file);
    expect(init?.headers).toMatchObject({ "Content-Type": "application/octet-stream" });
  });

  it("passes the abort signal to fetch", async () => {
    const fetchImpl = respond("{}", { type: "application/json" });
    const controller = new AbortController();
    await createApiClient(fetchImpl).request("GET", "/v1/health", { signal: controller.signal });
    expect(fetchImpl.mock.calls[0]?.[1]?.signal).toBe(controller.signal);
  });

  const failures: { name: string; kind: ApiErrorKind; status: number | null; fetchImpl: () => FetchLike }[] = [
    { name: "an HTML page served for a /v1 path", kind: "not-json", status: 200, fetchImpl: () => respond("<!doctype html>", { type: "text/html" }) },
    { name: "an HTML error page", kind: "not-json", status: 404, fetchImpl: () => respond("<html>Not Found</html>", { status: 404, type: "text/html" }) },
    { name: "a response without a content type", kind: "not-json", status: 200, fetchImpl: () => respond("{}", {}) },
    { name: "malformed JSON", kind: "invalid-json", status: 200, fetchImpl: () => respond("{broken", { type: "application/json" }) },
    { name: "a JSON error status", kind: "http", status: 500, fetchImpl: () => respond("{}", { status: 500, type: "application/json" }) },
    {
      name: "a network failure",
      kind: "network",
      status: null,
      fetchImpl: () =>
        vi.fn<FetchLike>(async () => {
          throw new TypeError("Failed to fetch");
        }),
    },
  ];

  it.each(failures)("throws ApiError kind $kind for $name", async ({ kind, status, fetchImpl }) => {
    const error = await failure(createApiClient(fetchImpl()).request("GET", "/v1/health"));
    expect(error.kind).toBe(kind);
    expect(error.status).toBe(status);
  });

  it("reports the error envelope message for a JSON failure", async () => {
    const fetchImpl = respond('{"status":"error","message":"Collection not found"}', { status: 404, type: "application/json" });
    const error = await failure(createApiClient(fetchImpl).request("GET", "/v1/collections/x"));
    expect(error.kind).toBe("http");
    expect(error.status).toBe(404);
    expect(error.message).toBe("Collection not found");
  });

  it("falls back to the detail field of an error body", async () => {
    const fetchImpl = respond('{"detail":"Path outside roots"}', { status: 403, type: "application/json" });
    const error = await failure(createApiClient(fetchImpl).request("POST", "/v1/experiments", { body: {} }));
    expect(error.message).toBe("Path outside roots");
  });

  it("keeps the parsed error body on the error", async () => {
    const fetchImpl = respond('{"message":"Graph refused","issues":[{"code":"x"}]}', { status: 422, type: "application/json" });
    const error = await failure(createApiClient(fetchImpl).request("POST", "/v1/pipelines/validate", { body: {} }));
    expect(error.body).toEqual({ message: "Graph refused", issues: [{ code: "x" }] });
  });

  it.each(["/health", "v1/health", "https://example.com/v1/health", "/v1/../admin"])(
    "refuses a path outside /v1: %s",
    async (path) => {
      const fetchImpl = vi.fn<FetchLike>();
      const error = await failure(createApiClient(fetchImpl).request("GET", path));
      expect(error.kind).toBe("invalid-path");
      expect(fetchImpl).not.toHaveBeenCalled();
    },
  );
});
