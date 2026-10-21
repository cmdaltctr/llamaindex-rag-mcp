/**
 * The one request function for the local `/v1` API.
 *
 * The single-origin server also serves the application page, so a wrong or
 * missing API route can come back as HTML. `request` checks the response
 * content type and raises `ApiError` instead of parsing HTML as JSON. Every
 * `api/*.ts` module is a thin typed layer over this function.
 *
 * After a server restart the session cookie is unknown and requests get 401.
 * With a session renewer, `request` signs in again once and sends the request
 * once more.
 */

export type ApiErrorKind = "invalid-path" | "network" | "not-json" | "invalid-json" | "http";

/**
 * A check in the page refused a value before or after a request. Its message
 * is written for the person, so a form may show it; every other error goes
 * through `describeError`.
 */
export class ClientRefusal extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ClientRefusal";
  }
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly path: string;
  /** The parsed JSON error body of an `http` failure; `undefined` for every other kind. */
  readonly body: unknown;

  constructor(kind: ApiErrorKind, message: string, path: string, status: number | null = null, body?: unknown) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.path = path;
    this.body = body;
  }
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

/** Signs in again after a 401; `createSessionRenewer` in `bootstrap.ts` builds one. */
export interface SessionRenewal {
  /** How many sign-ins have succeeded. A 401 for a request sent before the latest one needs only a retry. */
  readonly signIns: number;
  /** Resolves `true` when the server accepted the secret. */
  renew(): Promise<boolean>;
}

export type QueryValue = string | number | boolean | null | undefined;

export interface RequestInput {
  /** Appended to the path. `null` and `undefined` values are skipped. */
  query?: Record<string, QueryValue>;
  /** Sent as JSON, except a `Blob` (including `File`), which is sent as it is. */
  body?: unknown;
  /** Extra headers, for a raw body. */
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

export type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface ApiClient {
  request<T>(method: Method, path: string, input?: RequestInput): Promise<T>;
  /**
   * Opens a server-sent event stream. Resolves with the response when the
   * status is OK and the body is `text/event-stream`. Every other answer
   * throws `ApiError` with the same kinds as `request`; an OK status with
   * another content type throws kind `not-json` with that status.
   */
  stream(method: Method, path: string, input?: RequestInput): Promise<Response>;
}

/** The part of a query that an API function accepts from a caller. */
export interface CallOptions {
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

function mediaType(contentType: string | null): string {
  return contentType?.split(";")[0]?.trim().toLowerCase() ?? "";
}

function isJsonType(contentType: string | null): boolean {
  const type = mediaType(contentType);
  return type === "application/json" || type.endsWith("+json");
}

function envelopeMessage(body: unknown): string | null {
  if (typeof body !== "object" || body === null) return null;
  const record = body as Record<string, unknown>;
  const message = record.message ?? record.detail;
  return typeof message === "string" && message.length > 0 ? message : null;
}

function withQuery(path: string, query: Record<string, QueryValue> | undefined): string {
  if (query === undefined) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined) params.set(key, String(value));
  }
  const text = params.toString();
  return text === "" ? path : `${path}${path.includes("?") ? "&" : "?"}${text}`;
}

/**
 * Builds the client. `fetchImpl` is set once here; components never receive it.
 * `renewSession` signs in again after a 401 (see `createSessionRenewer`).
 */
export function createApiClient(
  fetchImpl: FetchLike = (input, init) => fetch(input, init),
  renewSession?: SessionRenewal,
): ApiClient {
  /** Sends the request, signs in again once after a 401, and returns the final response. */
  async function exchange(method: string, path: string, input: RequestInput, accept: string): Promise<Response> {
    const url = withQuery(path, input.query);
    if (!isApiPath(url)) {
      throw new ApiError("invalid-path", `Refused a request outside ${API_PREFIX}: ${path}`, path);
    }

    const headers: Record<string, string> = { Accept: accept, ...input.headers };
    let body: BodyInit | undefined;
    if (input.body instanceof Blob) {
      body = input.body;
    } else if (input.body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(input.body);
    }

    async function send(): Promise<Response> {
      try {
        return await fetchImpl(url, { method, headers, credentials: "same-origin", body, signal: input.signal });
      } catch (error) {
        const detail = error instanceof Error ? error.message : String(error);
        throw new ApiError("network", `Could not reach the local server: ${detail}`, path);
      }
    }

    const signInsBefore = renewSession?.signIns;
    let response = await send();
    if (response.status === 401 && renewSession !== undefined) {
      // A sign-in that finished while this request was out already gave a new cookie.
      const renewed = renewSession.signIns !== signInsBefore || (await renewSession.renew());
      if (renewed) response = await send();
    }
    return response;
  }

  /** Parses a JSON body, and throws the error envelope of a failed status. */
  async function parseJson<T>(path: string, response: Response): Promise<T> {
    const contentType = response.headers.get("content-type");
    if (!isJsonType(contentType)) {
      throw new ApiError(
        "not-json",
        `Expected JSON from ${path} but received ${contentType ?? "no content type"} (status ${response.status}).`,
        path,
        response.status,
      );
    }

    let parsed: unknown;
    try {
      parsed = await response.json();
    } catch {
      throw new ApiError("invalid-json", `The response from ${path} is not valid JSON.`, path, response.status);
    }

    if (!response.ok) {
      const message = envelopeMessage(parsed) ?? `Request to ${path} failed with status ${response.status}.`;
      throw new ApiError("http", message, path, response.status, parsed);
    }
    return parsed as T;
  }

  async function request<T>(method: string, path: string, input: RequestInput = {}): Promise<T> {
    return parseJson<T>(path, await exchange(method, path, input, "application/json"));
  }

  async function stream(method: string, path: string, input: RequestInput = {}): Promise<Response> {
    const response = await exchange(method, path, input, "text/event-stream");
    const contentType = response.headers.get("content-type");
    if (response.ok && mediaType(contentType) === "text/event-stream") return response;
    if (!response.ok) await parseJson(path, response);
    await response.body?.cancel().catch(() => undefined);
    throw new ApiError(
      "not-json",
      `Expected an event stream from ${path} but received ${contentType ?? "no content type"} (status ${response.status}).`,
      path,
      response.status,
    );
  }

  return { request, stream };
}
