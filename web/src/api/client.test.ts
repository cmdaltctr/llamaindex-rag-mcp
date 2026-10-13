import { describe, expect, it, vi } from "vitest";
import { ApiError, getHealth, getJson } from "./client";

function respond(body: string, init: { status?: number; type?: string }) {
  const headers: Record<string, string> = init.type === undefined ? {} : { "content-type": init.type };
  return vi.fn(async () => new Response(body, { status: init.status ?? 200, headers }));
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
    await expect(getHealth(fetchImpl)).resolves.toEqual({ status: "ok" });
    expect(fetchImpl).toHaveBeenCalledWith(
      "/v1/health",
      expect.objectContaining({ headers: expect.objectContaining({ Accept: "application/json" }) }),
    );
  });

  it("rejects an HTML page served for a /v1 path", async () => {
    const fetchImpl = respond("<!doctype html><html></html>", { type: "text/html; charset=utf-8" });
    const error = await failure(getJson("/v1/health", { fetchImpl }));
    expect(error.kind).toBe("not-json");
    expect(error.status).toBe(200);
  });

  it("rejects an HTML error page without parsing it", async () => {
    const fetchImpl = respond("<html>Not Found</html>", { status: 404, type: "text/html" });
    const error = await failure(getJson("/v1/collections", { fetchImpl }));
    expect(error.kind).toBe("not-json");
    expect(error.status).toBe(404);
  });

  it("rejects a response without a content type", async () => {
    const fetchImpl = respond("{}", {});
    const error = await failure(getJson("/v1/health", { fetchImpl }));
    expect(error.kind).toBe("not-json");
  });

  it("reports the error envelope message for a JSON failure", async () => {
    const fetchImpl = respond('{"status":"error","message":"Collection not found"}', {
      status: 404,
      type: "application/json",
    });
    const error = await failure(getJson("/v1/collections/x", { fetchImpl }));
    expect(error.kind).toBe("http");
    expect(error.status).toBe(404);
    expect(error.message).toBe("Collection not found");
  });

  it("reports malformed JSON", async () => {
    const fetchImpl = respond("{broken", { type: "application/json" });
    const error = await failure(getJson("/v1/health", { fetchImpl }));
    expect(error.kind).toBe("invalid-json");
  });

  it("reports a network failure", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const error = await failure(getJson("/v1/health", { fetchImpl }));
    expect(error.kind).toBe("network");
    expect(error.status).toBeNull();
  });

  it.each(["/health", "v1/health", "https://example.com/v1/health", "/v1/../admin"])(
    "refuses a path outside /v1: %s",
    async (path) => {
      const fetchImpl = vi.fn();
      const error = await failure(getJson(path, { fetchImpl }));
      expect(error.kind).toBe("invalid-path");
      expect(fetchImpl).not.toHaveBeenCalled();
    },
  );
});
