/**
 * Typed helpers for the local `/v1` API.
 *
 * The single-origin server also serves the application page, so a wrong or
 * missing API route can come back as HTML. These helpers check the response
 * content type and raise `ApiError` instead of parsing HTML as JSON.
 */

export type ApiErrorKind = "invalid-path" | "network" | "not-json" | "invalid-json" | "http";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly path: string;

  constructor(kind: ApiErrorKind, message: string, path: string, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.path = path;
  }
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface RequestOptions {
  fetchImpl?: FetchLike;
  signal?: AbortSignal;
}

const API_PREFIX = "/v1/";
const PATH_BASE = "http://omrg.invalid";

/** True only for a same-origin path under `/v1/` that needs no normalisation. */
function isApiPath(path: string): boolean {
  if (!path.startsWith(API_PREFIX)) return false;
  let url: URL;
  try {
    url = new URL(path, PATH_BASE);
  } catch {
    return false;
  }
  return url.origin === PATH_BASE && url.pathname.startsWith(API_PREFIX) && url.pathname + url.search === path;
}

function isJsonType(contentType: string | null): boolean {
  if (contentType === null) return false;
  const mediaType = contentType.split(";")[0]?.trim().toLowerCase() ?? "";
  return mediaType === "application/json" || mediaType.endsWith("+json");
}

function envelopeMessage(body: unknown): string | null {
  if (typeof body !== "object" || body === null) return null;
  const message = (body as Record<string, unknown>).message;
  return typeof message === "string" && message.length > 0 ? message : null;
}

/** Sends a GET request to a `/v1/` path and returns the parsed JSON body. */
export async function getJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  if (!isApiPath(path)) {
    throw new ApiError("invalid-path", `Refused a request outside ${API_PREFIX}: ${path}`, path);
  }

  const fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
  let response: Response;
  try {
    response = await fetchImpl(path, {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
      signal: options.signal,
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new ApiError("network", `Could not reach the local server: ${detail}`, path);
  }

  const contentType = response.headers.get("content-type");
  if (!isJsonType(contentType)) {
    throw new ApiError(
      "not-json",
      `Expected JSON from ${path} but received ${contentType ?? "no content type"} (status ${response.status}).`,
      path,
      response.status,
    );
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError("invalid-json", `The response from ${path} is not valid JSON.`, path, response.status);
  }

  if (!response.ok) {
    const message = envelopeMessage(body) ?? `Request to ${path} failed with status ${response.status}.`;
    throw new ApiError("http", message, path, response.status);
  }
  return body as T;
}

/**
 * Placeholder health check. The response shape is not part of the reviewed
 * contract yet, so callers receive an untyped record.
 */
export function getHealth(fetchImpl?: FetchLike): Promise<Record<string, unknown>> {
  return getJson<Record<string, unknown>>("/v1/health", { fetchImpl });
}
