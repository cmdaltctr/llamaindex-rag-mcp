import { screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { mockReactFlow } from "./studio/test/mockReactFlow";
import { startApp } from "./test/startApp";
import { documentsServer, type Handler } from "./test/fakeDocumentsServer";

beforeAll(mockReactFlow);

afterEach(() => {
  vi.restoreAllMocks();
});

const HTML = "<!doctype html><html><body>Bad gateway stack trace at line 3</body></html>";
const RAW_FRAGMENTS = ["Expected JSON", "text/html", "<!doctype", "<html>", "stack trace", "status 502", "status 200", "/v1/", "Failed to fetch", "TypeError"];

/** A server whose every route answers with an HTML page, like a proxy error. */
function htmlServer() {
  const html: Handler = () => new Response(HTML, { status: 502, headers: { "content-type": "text/html" } });
  return documentsServer(
    Object.fromEntries(
      ["GET /v1/collections", "GET /v1/integrations", "GET /v1/pipelines", "GET /v1/profiles", "GET /v1/profiles/papers-search", "GET /v1/experiments", "GET /v1/runs", "GET /v1/plugins", "GET /v1/connections", "GET /v1/mcp", "GET /v1/session", "GET /v1/roots", "GET /v1/pipeline-operations", "GET /v1/settings/web-port", "GET /v1/health"].map((key) => [key, html]),
    ),
  );
}

/** A server that cannot be reached at all. */
function offlineServer() {
  const server = documentsServer();
  server.fetchImpl.mockImplementation(async () => {
    throw new TypeError("Failed to fetch");
  });
  return server;
}

const HASHES = [
  "#/home",
  "#/chat",
  "#/chat/papers",
  "#/knowledge-base",
  "#/knowledge-base/documents",
  "#/studio",
  "#/studio/papers-search/search",
  "#/experiments",
  "#/experiments/runs/r1",
  "#/integrations",
  "#/settings",
];

describe.each([
  ["an HTML error page", htmlServer],
  ["an unreachable server", offlineServer],
])("every area with %s", (_label, makeServer) => {
  it.each(HASHES)("shows no parser, status or network text at %s", async (hash) => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    startApp(hash, makeServer());
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument());
    // Let every failing request settle and render its failure.
    await new Promise((resolve) => setTimeout(resolve, 150));
    const text = document.body.textContent ?? "";
    for (const fragment of RAW_FRAGMENTS) expect(text, `${hash} shows "${fragment}"`).not.toContain(fragment);
  });
});
