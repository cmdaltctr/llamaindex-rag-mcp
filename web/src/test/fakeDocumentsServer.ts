import { vi } from "vitest";
import type { FetchLike } from "../api/client";
import type { UploadLimitState } from "../api/settings";

export interface Call {
  method: string;
  path: string;
  body: unknown;
  headers: Headers;
}

/** A handler returns a Response, or any value that is sent as JSON with status 200. */
export type Handler = (body: Record<string, unknown>, call: Call) => unknown;
// A handler may also return a promise, to hold a response back.

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

export const COLLECTIONS = [
  { name: "documents", document_count: 3, chunk_count: 12, profile: "documents", store: { name: "lancedb", label: "LanceDB" } },
  { name: "notes", document_count: 1, chunk_count: 2, profile: null, store: { name: "lancedb", label: "LanceDB" } },
];

export const SOURCES = [
  { source: "/srv/docs/present.md", source_id: "sid-present", chunks: 5, orphaned: false },
  { source: "/srv/docs/gone.md", source_id: "sid-gone", chunks: 4, orphaned: true },
  { source: "relative/unknown.md", source_id: null, chunks: 3, orphaned: null },
];

export const ROOTS = [
  { id: "root_operator", path: "/srv/docs", kind: "operator" },
  { id: "root_managed", path: "/home/u/.omrg/workspace/uploads", kind: "managed" },
];

/** `GET /v1/settings/upload-limit` with no saved value: the 50 MiB default. */
export const UPLOAD_LIMIT: UploadLimitState = { status: "ok", max_bytes: 50 * 1024 * 1024, source: "default", saved_mib: null, default_mib: 50, min_mib: 1, max_mib: 2048 };

const DEFAULTS: Record<string, Handler> = {
  "GET /v1/collections": () => COLLECTIONS,
  "GET /v1/collections/documents/documents": () => SOURCES,
  "GET /v1/collections/notes/documents": () => [],
  "GET /v1/roots": () => ({ status: "ok", roots: ROOTS }),
  "GET /v1/settings/upload-limit": () => UPLOAD_LIMIT,
};

/**
 * In-memory stand-in for the document routes. Keys are `METHOD /path` without
 * the query string. Unknown routes answer with a 404 error envelope.
 */
export function documentsServer(handlers: Record<string, Handler> = {}) {
  const calls: Call[] = [];
  const routes = { ...DEFAULTS, ...handlers };
  const fetchImpl = vi.fn<FetchLike>(async (path, init) => {
    const method = init?.method ?? "GET";
    const raw = init?.body;
    const body = typeof raw === "string" ? (JSON.parse(raw) as Record<string, unknown>) : raw ?? null;
    const call: Call = { method, path, body, headers: new Headers(init?.headers) };
    calls.push(call);
    const handler = routes[`${method} ${path.split("?")[0]}`];
    if (handler === undefined) return json({ status: "error", message: `No fake route for ${method} ${path}` }, 404);
    const result = await handler((body ?? {}) as Record<string, unknown>, call);
    return result instanceof Response ? result : json(result);
  });

  return {
    calls,
    fetchImpl,
    /** Calls matching a method and a path prefix. */
    find(method: string, prefix: string): Call[] {
      return calls.filter((c) => c.method === method && c.path.startsWith(prefix));
    },
  };
}
