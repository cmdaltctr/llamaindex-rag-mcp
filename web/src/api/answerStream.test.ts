import { describe, expect, it, vi } from "vitest";
import { chunkStream, controlledStream, sseFrame, stageFrame, streamResponse } from "../test/fakeStream";
import { json } from "../test/fakeDocumentsServer";
import { answerCollectionStreaming, readFrames, type AnswerStage } from "./answerStream";
import { ApiError, createApiClient, type FetchLike } from "./client";

const RESULT = { status: "ok", query: "q", answer: "a", citations: [], evidence: [], failure_stage: null, error: null, completion_source: "server" };
const STREAM_PATH = "/v1/collections/documents/answer/stream";
const BLOCKING_PATH = "/v1/collections/documents/answer";

async function collect(body: ReadableStream<Uint8Array>, events = ["stage", "result"]) {
  const frames = [];
  for await (const frame of readFrames(body, events)) frames.push(frame);
  return frames;
}

describe("readFrames", () => {
  it("joins a frame split across chunks", async () => {
    const frames = await collect(chunkStream(["event: st", "age\ndata: {\"stage\":", "\"searching\"}\n", "\nevent: result\ndata: {}\n\n"]));
    expect(frames).toEqual([
      { event: "stage", data: '{"stage":"searching"}' },
      { event: "result", data: "{}" },
    ]);
  });

  it("decodes a multi-byte character split across chunks", async () => {
    const bytes = new TextEncoder().encode('event: result\ndata: {"answer":"café ✓"}\n\n');
    const cut = bytes.indexOf(0xc3) + 1;
    const frames = await collect(chunkStream([bytes.slice(0, cut), bytes.slice(cut)]));
    expect(frames).toEqual([{ event: "result", data: '{"answer":"café ✓"}' }]);
  });

  it("ignores comment lines and unknown events", async () => {
    const frames = await collect(chunkStream([": keep-alive\n\n", "event: ping\ndata: 1\n\n", ": note\nevent: stage\ndata: x\n\n"]));
    expect(frames).toEqual([{ event: "stage", data: "x" }]);
  });

  it("keeps a final frame that has no trailing blank line", async () => {
    const frames = await collect(chunkStream(["event: stage\ndata: a\n\nevent: result\ndata: b"]));
    expect(frames).toEqual([
      { event: "stage", data: "a" },
      { event: "result", data: "b" },
    ]);
  });

  it("reads CRLF line ends and joins data lines", async () => {
    const frames = await collect(chunkStream(["event: result\r\ndata: one\r\ndata: two\r\n\r\nevent: stage\r", "\ndata: x\r\n\r\n"]));
    expect(frames).toEqual([
      { event: "result", data: "one\ntwo" },
      { event: "stage", data: "x" },
    ]);
  });
});

type Route = (init: RequestInit | undefined) => Response | Promise<Response>;

function server(stream: Route, blocking: Route = () => json(RESULT)) {
  const fetchImpl = vi.fn<FetchLike>(async (path, init) => {
    if (path === STREAM_PATH) return stream(init);
    if (path === BLOCKING_PATH) return blocking(init);
    return json({ status: "error", message: "no route" }, 404);
  });
  const calls = (path: string) => fetchImpl.mock.calls.filter(([p]) => p === path).length;
  return { api: createApiClient(fetchImpl), fetchImpl, calls };
}

async function failure(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  throw new Error("expected the answer to fail");
}

describe("answerCollectionStreaming", () => {
  it("reports stages in frame order and returns the result", async () => {
    const { api, fetchImpl, calls } = server(() =>
      streamResponse([stageFrame("searching", 1), stageFrame("writing", 2), stageFrame("citing", 3), sseFrame("result", RESULT)]),
    );
    const stages: AnswerStage[] = [];
    const result = await answerCollectionStreaming(api, "documents", { query: "q" }, { onStage: (stage) => stages.push(stage) });
    expect(stages).toEqual(["searching", "writing", "citing"]);
    expect(result).toEqual(RESULT);
    expect(calls(BLOCKING_PATH)).toBe(0);
    const init = fetchImpl.mock.calls[0]![1]!;
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ query: "q", top_k: null, rerank: null, hybrid: null, metadata_filter: null });
    expect(new Headers(init.headers).get("Accept")).toBe("text/event-stream");
  });

  it("ignores a stage frame with an unknown stage name", async () => {
    const { api } = server(() => streamResponse([stageFrame("thinking", 1), stageFrame("searching", 2), sseFrame("result", RESULT)]));
    const stages: AnswerStage[] = [];
    await answerCollectionStreaming(api, "documents", { query: "q" }, { onStage: (stage) => stages.push(stage) });
    expect(stages).toEqual(["searching"]);
  });

  it("throws an http ApiError with the server message for a 400", async () => {
    const { api, calls } = server(() => json({ status: "error", error_type: "validation", message: "No saved Answer graph." }, 400));
    const error = await failure(answerCollectionStreaming(api, "documents", { query: "q" }));
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ kind: "http", status: 400, message: "No saved Answer graph." });
    expect(calls(BLOCKING_PATH)).toBe(0);
  });

  it.each([
    ["a missing body reader", () => new Response(null, { status: 200, headers: { "content-type": "text/event-stream" } })],
    ["a 404", () => json({ status: "error", message: "Not Found" }, 404)],
    ["a 405", () => json({ status: "error", message: "Method Not Allowed" }, 405)],
    ["an HTML 404", () => new Response("<html></html>", { status: 404, headers: { "content-type": "text/html" } })],
    ["a non-stream content type", () => json(RESULT)],
  ])("falls back to the blocking route once for %s", async (_name, stream) => {
    const { api, calls } = server(stream);
    const result = await answerCollectionStreaming(api, "documents", { query: "q" });
    expect(result).toEqual(RESULT);
    expect(calls(STREAM_PATH)).toBe(1);
    expect(calls(BLOCKING_PATH)).toBe(1);
  });

  it("aborts the stream request before it falls back for a missing body reader", async () => {
    let signal: AbortSignal | null | undefined;
    const { api } = server((init) => {
      signal = init?.signal;
      return new Response(null, { status: 200, headers: { "content-type": "text/event-stream" } });
    });
    await answerCollectionStreaming(api, "documents", { query: "q" });
    expect(signal?.aborted).toBe(true);
  });

  it.each([400, 403, 503])("does not fall back for a %i", async (status) => {
    const { api, calls } = server(() => json({ status: "error", message: "refused" }, status));
    const error = await failure(answerCollectionStreaming(api, "documents", { query: "q" }));
    expect(error).toMatchObject({ kind: "http", status });
    expect(calls(BLOCKING_PATH)).toBe(0);
  });

  it("does not fall back for a network failure", async () => {
    const { api, calls } = server(() => Promise.reject(new TypeError("Failed to fetch")));
    const error = await failure(answerCollectionStreaming(api, "documents", { query: "q" }));
    expect(error).toMatchObject({ kind: "network" });
    expect(calls(BLOCKING_PATH)).toBe(0);
  });

  it("throws a network ApiError when the stream ends with no result, without calling the blocking route", async () => {
    const { api, calls } = server(() => streamResponse([stageFrame("searching", 1), stageFrame("writing", 2)]));
    const stages: AnswerStage[] = [];
    const error = await failure(answerCollectionStreaming(api, "documents", { query: "q" }, { onStage: (stage) => stages.push(stage) }));
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ kind: "network" });
    expect(stages).toEqual(["searching", "writing"]);
    expect(calls(BLOCKING_PATH)).toBe(0);
  });

  it("throws an invalid-json ApiError for a result frame that is not JSON", async () => {
    const { api } = server(() => streamResponse(["event: result\ndata: {not json\n\n"]));
    const error = await failure(answerCollectionStreaming(api, "documents", { query: "q" }));
    expect(error).toMatchObject({ kind: "invalid-json" });
  });

  it("stops reading when the signal aborts", async () => {
    const stream = controlledStream();
    const { api, calls } = server(() => stream.response);
    const controller = new AbortController();
    const stages: AnswerStage[] = [];
    const pending = answerCollectionStreaming(api, "documents", { query: "q" }, { onStage: (stage) => stages.push(stage), signal: controller.signal });
    stream.push(stageFrame("searching", 1));
    await vi.waitFor(() => expect(stages).toEqual(["searching"]));
    controller.abort();
    const error = await failure(pending);
    expect((error as Error).name).toBe("AbortError");
    expect(stages).toEqual(["searching"]);
    expect(calls(BLOCKING_PATH)).toBe(0);
  });
});
