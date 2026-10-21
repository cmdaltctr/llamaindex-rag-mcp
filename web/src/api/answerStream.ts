/**
 * The streamed answer: `POST .../answer/stream` sends `stage` frames while the
 * answer runs, then one `result` frame with the same body as `POST .../answer`.
 *
 * Stage progress is a convenience. When the browser cannot read a streamed
 * body, or the server has no stream route, the answer comes from the blocking
 * route instead. Every other failure is thrown: a refusal or an outage would
 * only repeat there, and a second request would start a second paid answer.
 */
import { ApiError, type ApiClient } from "./client";
import { answerBody, answerCollection, collectionPath, type AnswerResult, type QueryControls } from "./documents";

/** The stages of one answer, in the order the server reports them. */
export const ANSWER_STAGES = ["searching", "writing", "citing", "verifying"] as const;
export type AnswerStage = (typeof ANSWER_STAGES)[number];

export interface EventFrame {
  event: string;
  data: string;
}

function isStage(value: unknown): value is AnswerStage {
  return typeof value === "string" && (ANSWER_STAGES as readonly string[]).includes(value);
}

/**
 * Reads server-sent event frames from a body. Frames end at a blank line; a
 * last frame with no blank line after it is kept. Comment lines and events
 * not named in `events` are dropped. Multiple `data` lines join with `\n`.
 * An abort of `signal` cancels the read, which then ends.
 */
export async function* readFrames(body: ReadableStream<Uint8Array>, events: readonly string[], signal?: AbortSignal): AsyncGenerator<EventFrame> {
  const reader = body.getReader();
  // A constructed or proxied body may ignore the fetch signal, so the abort cancels the reader too.
  const cancel = () => void reader.cancel().catch(() => undefined);
  signal?.addEventListener("abort", cancel, { once: true });
  const decoder = new TextDecoder();
  let buffer = "";
  let event = "message";
  let data: string[] = [];

  function* take(line: string): Generator<EventFrame> {
    if (line === "") {
      if (data.length > 0 && events.includes(event)) yield { event, data: data.join("\n") };
      event = "message";
      data = [];
      return;
    }
    if (line.startsWith(":")) return;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }

  try {
    for (;;) {
      const { done, value } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      // A lone CR at the end may be the first half of CRLF, so it waits for the next chunk.
      const lines = buffer.split(/\r\n|\r(?!$)|\n/);
      buffer = lines.pop() ?? "";
      for (const line of lines) yield* take(line);
      if (done) break;
    }
    if (buffer !== "") yield* take(buffer.replace(/\r$/, ""));
    yield* take("");
  } finally {
    signal?.removeEventListener("abort", cancel);
    reader.releaseLock();
  }
}

export interface StreamOptions {
  /** Called once for each stage frame, in frame order. */
  onStage?: (stage: AnswerStage) => void;
  signal?: AbortSignal;
}

function abortError(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException("The answer request was aborted.", "AbortError");
}

/** True when the stream route is missing or the reply is not a stream, so the blocking route may answer instead. */
function canFallBack(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status === null) return false;
  if (error.status === 404 || error.status === 405) return true;
  return error.kind === "not-json" && error.status >= 200 && error.status < 300;
}

/**
 * Asks one collection a question through the stream route and returns the
 * answer result. Falls back to `answerCollection` only before any frame, and
 * only when the stream is unavailable (see `canFallBack`).
 */
export async function answerCollectionStreaming(
  api: ApiClient,
  collection: string,
  controls: QueryControls,
  { onStage, signal }: StreamOptions = {},
): Promise<AnswerResult> {
  const path = collectionPath(collection, "/answer/stream");
  // Our own controller, so the stream request can close when the blocking route takes over.
  const local = new AbortController();
  const forward = () => local.abort(signal?.reason);
  if (signal?.aborted) forward();
  signal?.addEventListener("abort", forward, { once: true });
  try {
    let response: Response;
    try {
      response = await api.stream("POST", path, { body: answerBody(controls), signal: local.signal });
    } catch (error) {
      if (signal?.aborted) throw abortError(signal);
      if (!canFallBack(error)) throw error;
      return await answerCollection(api, collection, controls, { signal });
    }

    if (typeof response.body?.getReader !== "function") {
      local.abort();
      return await answerCollection(api, collection, controls, { signal });
    }
    try {
      for await (const frame of readFrames(response.body, ["stage", "result"], local.signal)) {
        if (local.signal.aborted) break;
        if (frame.event === "result") {
          try {
            return JSON.parse(frame.data) as AnswerResult;
          } catch {
            throw new ApiError("invalid-json", `The result frame from ${path} is not valid JSON.`, path, response.status);
          }
        }
        let parsed: unknown;
        try {
          parsed = JSON.parse(frame.data);
        } catch {
          continue;
        }
        const stage = (parsed as { stage?: unknown } | null)?.stage;
        if (isStage(stage)) onStage?.(stage);
      }
    } catch (error) {
      if (signal?.aborted) throw abortError(signal);
      if (error instanceof ApiError) throw error;
      const detail = error instanceof Error ? error.message : String(error);
      throw new ApiError("network", `The answer stream from ${path} broke: ${detail}`, path, response.status);
    }
    if (signal?.aborted) throw abortError(signal);
    throw new ApiError("network", `The answer stream from ${path} ended with no result.`, path, response.status);
  } finally {
    signal?.removeEventListener("abort", forward);
  }
}
