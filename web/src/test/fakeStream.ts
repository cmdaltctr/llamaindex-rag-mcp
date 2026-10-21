/** Builders for a streamed `text/event-stream` response that tests feed by hand. */

const encoder = new TextEncoder();

/** One server-sent event frame, with its trailing blank line. */
export function sseFrame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** A `stage` frame as the answer stream route sends it. */
export function stageFrame(stage: string, sequence: number, elapsedMs = sequence * 100): string {
  return sseFrame("stage", { stage, sequence, elapsed_ms: elapsedMs });
}

/** A body stream that emits the given chunks, then ends. */
export function chunkStream(chunks: (string | Uint8Array)[]): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      controller.close();
    },
  });
}

/** A complete `text/event-stream` response. */
export function streamResponse(chunks: (string | Uint8Array)[], status = 200): Response {
  return new Response(chunkStream(chunks), { status, headers: { "content-type": "text/event-stream" } });
}

/**
 * A stream response whose frames the test sends one at a time, so it can look
 * at the page between frames.
 */
export function controlledStream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  let cancelled = false;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
    cancel() {
      cancelled = true;
    },
  });
  return {
    response: new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } }),
    /** True once the reader cancelled the body, for example after an abort. */
    get cancelled() {
      return cancelled;
    },
    /** Sends text; does nothing once the reader cancelled the body. */
    push(text: string) {
      if (!cancelled) controller.enqueue(encoder.encode(text));
    },
    close() {
      if (!cancelled) controller.close();
    },
  };
}
