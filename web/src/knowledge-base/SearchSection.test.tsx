import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { documentsServer, json, type Handler } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

function hit(overrides: Record<string, unknown>) {
  return {
    score: 0.8123, score_kind: "dense_similarity_v1", source: "/srv/docs/present.md", page_label: null, text: "Body text",
    reranked: false, metadata: {}, source_id: "sid-present", source_version: "v1", chunk_id: "c-2", source_chunk_index: 2, source_chunk_count: 4,
    ...overrides,
  };
}

function chunkView(id: string, index: number, text: string) {
  return {
    chunk_id: id, source_id: "sid-present", source_version: "v1", source_chunk_index: index,
    source_chunk_count: 4, source: "/srv/docs/present.md", page_label: null, text, metadata: {},
  };
}

const CHUNK = {
  status: "ok", collection: "documents", text_format: "plain",
  chunk: chunkView("c-2", 2, "Second chunk"), previous: [chunkView("c-1", 1, "First chunk")], next: [chunkView("c-3", 3, "Third chunk")],
};

async function setup(handlers: Record<string, Handler> = {}) {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  const { server } = startApp(
    "#/knowledge-base/documents",
    documentsServer({
      "POST /v1/collections/documents/search": () => [
        hit({}),
        hit({ score: 0.016, score_kind: "rrf_v1", reranked: true, source: "/srv/docs/gone.md", source_id: "sid-gone", chunk_id: "g-1", text: "<b>not markup</b>" }),
        hit({ score: undefined, score_kind: undefined, source: "relative/unknown.md", source_id: null, chunk_id: null, text: "Legacy row" }),
      ],
      "GET /v1/collections/documents/chunks/c-2": () => CHUNK,
      ...handlers,
    }),
  );
  const user = userEvent.setup();
  await screen.findByRole("table", { name: "Sources in documents" });
  await user.click(screen.getByRole("button", { name: "Search" }));
  return { server, user };
}

async function search(user: ReturnType<typeof userEvent.setup>, query = "lineage") {
  await user.type(screen.getByRole("searchbox", { name: "Query" }), query);
  await user.click(screen.getByRole("button", { name: "Run search" }));
  return screen.findByRole("list", { name: "Search results" });
}

async function choose(user: ReturnType<typeof userEvent.setup>, name: string, option: string) {
  await user.click(screen.getByRole("combobox", { name }));
  await user.click(await screen.findByRole("option", { name: option }));
}

describe("search controls", () => {
  it("is scoped to the open project and sends null for every control left to the profile", async () => {
    const { server, user } = await setup();
    expect(screen.queryByRole("combobox", { name: "Collection" })).not.toBeInTheDocument();
    await search(user);
    expect(server.find("POST", "/v1/collections/documents/search")[0]?.body).toEqual({
      query: "lineage", top_k: null, rerank: null, hybrid: null, metadata_filter: null,
    });
  });

  it("sends explicit overrides and the metadata filter only when the user sets them", async () => {
    const { server, user } = await setup();
    await user.type(screen.getByRole("spinbutton", { name: "Results (top_k)" }), "5");
    await choose(user, "Rerank", "Off");
    await choose(user, "Hybrid", "On");
    await user.type(screen.getByRole("textbox", { name: "Metadata filter (JSON)" }), '{{"lang": "ar"}');
    await search(user);
    expect(server.find("POST", "/v1/collections/documents/search")[0]?.body).toEqual({
      query: "lineage", top_k: 5, rerank: false, hybrid: true, metadata_filter: { lang: "ar" },
    });
  });

  it("refuses a metadata filter that is not a JSON object", async () => {
    const { server, user } = await setup();
    await user.type(screen.getByRole("textbox", { name: "Metadata filter (JSON)" }), "[[1]");
    await user.type(screen.getByRole("searchbox", { name: "Query" }), "q");
    await user.click(screen.getByRole("button", { name: "Run search" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The metadata filter must be a JSON object.");
    expect(server.find("POST", "/v1/collections/documents/search")).toHaveLength(0);
  });

  it("asks for a query before it searches", async () => {
    const { server, user } = await setup();
    await user.click(screen.getByRole("button", { name: "Run search" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a query.");
    expect(server.find("POST", "/v1/collections/documents/search")).toHaveLength(0);
  });
});

describe("search results", () => {
  it("lists chunks in rank order, each with score, score kind, source and machine-local status", async () => {
    const { user } = await setup();
    const items = within(await search(user)).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("0.8123");
    expect(items[0]).toHaveTextContent("Dense similarity (dense_similarity_v1)");
    expect(items[0]).toHaveTextContent("Present on this machine");
    expect(items[1]).toHaveTextContent("Reciprocal rank fusion (rrf_v1)");
    expect(items[1]).toHaveTextContent("Reranked");
    expect(items[1]).toHaveTextContent("Missing on this machine");
    // Server text is shown as text, never as markup.
    expect(items[1]).toHaveTextContent("<b>not markup</b>");
    expect(items[1]?.querySelector("b")).toBeNull();
    expect(items[2]).toHaveTextContent("Not ranked: neighbour context");
    expect(items[2]).toHaveTextContent("Unknown on this machine");
  });

  it("opens the stored chunk in the chunk viewer", async () => {
    const { server, user } = await setup();
    const results = await search(user);
    await user.click(within(results).getAllByRole("button", { name: "Show chunk" })[0]!);
    const viewer = await screen.findByRole("dialog", { name: "Stored chunk" });
    expect(await within(viewer).findByText("Second chunk")).toBeInTheDocument();
    expect(within(viewer).getByText(/Chunk 3 of 4/)).toBeInTheDocument();
    expect(within(viewer).getByText("/srv/docs/present.md")).toBeInTheDocument();
    expect(server.find("GET", "/v1/collections/documents/chunks/c-2")[0]?.path).toBe("/v1/collections/documents/chunks/c-2?window=1");
  });

  it("offers no chunk link for a legacy row without a chunk id", async () => {
    const { user } = await setup();
    const items = within(await search(user)).getAllByRole("listitem");
    expect(within(items[2]!).queryByRole("button", { name: "Show chunk" })).not.toBeInTheDocument();
    expect(items[2]).toHaveTextContent("No stored chunk ID");
  });

  it("says so when nothing matches", async () => {
    const { user } = await setup({ "POST /v1/collections/documents/search": () => [] });
    await user.type(screen.getByRole("searchbox", { name: "Query" }), "zzz");
    await user.click(screen.getByRole("button", { name: "Run search" }));
    expect(await screen.findByText(/no results/i)).toBeInTheDocument();
  });

  it("shows a friendly failure with Retry and never the raw text", async () => {
    const { user } = await setup({ "POST /v1/collections/documents/search": () => json({ status: "error", message: "RAW store offline" }, 500) });
    await user.type(screen.getByRole("searchbox", { name: "Query" }), "q");
    await user.click(screen.getByRole("button", { name: "Run search" }));
    const alert = await screen.findByRole("alert");
    expect(alert).not.toHaveTextContent("RAW");
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
