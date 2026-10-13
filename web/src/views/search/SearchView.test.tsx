import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { documentsServer, type Handler } from "../test/fakeDocumentsServer";
import { SearchView } from "./SearchView";

function hit(overrides: Record<string, unknown>) {
  return {
    score: 0.8123,
    score_kind: "dense_similarity_v1",
    source: "/srv/docs/present.md",
    page_label: null,
    text: "Body text",
    reranked: false,
    metadata: {},
    source_id: "sid-present",
    source_version: "v1",
    chunk_id: "c-2",
    source_chunk_index: 2,
    source_chunk_count: 4,
    ...overrides,
  };
}

function chunkView(id: string, index: number, text: string) {
  return {
    chunk_id: id, source_id: "sid-present", source_version: "v1", source_chunk_index: index,
    source_chunk_count: 4, source: "/srv/docs/present.md", page_label: null, text, metadata: {},
  };
}

const CHUNKS: Record<string, unknown> = {
  "c-2": { status: "ok", collection: "documents", text_format: "plain", chunk: chunkView("c-2", 2, "Second chunk"), previous: [chunkView("c-1", 1, "First chunk")], next: [chunkView("c-3", 3, "Third chunk")] },
  "c-3": { status: "ok", collection: "documents", text_format: "plain", chunk: chunkView("c-3", 3, "Third chunk"), previous: [chunkView("c-2", 2, "Second chunk")], next: [] },
};

function setup(handlers: Record<string, Handler> = {}) {
  const server = documentsServer({
    "POST /v1/collections/documents/search": () => [
      hit({}),
      hit({ score: 0.016, score_kind: "rrf_v1", source: "/srv/docs/gone.md", source_id: "sid-gone", chunk_id: "g-1", text: "<b>not markup</b>" }),
      hit({ score: undefined, score_kind: undefined, source: "relative/unknown.md", source_id: null, chunk_id: null, text: "Legacy row" }),
    ],
    "GET /v1/collections/documents/chunks/c-2": () => CHUNKS["c-2"],
    "GET /v1/collections/documents/chunks/c-3": () => CHUNKS["c-3"],
    ...handlers,
  });
  render(<SearchView fetchImpl={server.fetchImpl} />);
  return { server, user: userEvent.setup() };
}

async function search(user: ReturnType<typeof userEvent.setup>, query = "lineage") {
  await screen.findByRole("option", { name: "documents" });
  await user.type(screen.getByRole("searchbox", { name: "Query" }), query);
  await user.click(screen.getByRole("button", { name: "Search" }));
  return screen.findByRole("list", { name: "Search results" });
}

describe("Search controls", () => {
  it("sends null for every control left to the profile", async () => {
    const { server, user } = setup();
    await search(user);
    expect(server.find("POST", "/v1/collections/documents/search")[0]?.body).toEqual({
      query: "lineage", top_k: null, rerank: null, hybrid: null, metadata_filter: null,
    });
  });

  it("sends explicit overrides only when the user sets them", async () => {
    const { server, user } = setup();
    await screen.findByRole("option", { name: "documents" });
    await user.type(screen.getByRole("spinbutton", { name: "Results (top_k)" }), "5");
    await user.selectOptions(screen.getByRole("combobox", { name: "Rerank" }), "off");
    await user.selectOptions(screen.getByRole("combobox", { name: "Hybrid" }), "on");
    await user.type(screen.getByRole("textbox", { name: "Metadata filter (JSON)" }), '{{"lang": "ar"}');
    await search(user);
    expect(server.find("POST", "/v1/collections/documents/search")[0]?.body).toEqual({
      query: "lineage", top_k: 5, rerank: false, hybrid: true, metadata_filter: { lang: "ar" },
    });
  });

  it("refuses a metadata filter that is not a JSON object", async () => {
    const { server, user } = setup();
    await screen.findByRole("option", { name: "documents" });
    await user.type(screen.getByRole("textbox", { name: "Metadata filter (JSON)" }), "[[1]");
    await user.type(screen.getByRole("searchbox", { name: "Query" }), "q");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The metadata filter must be a JSON object.");
    expect(server.find("POST", "/v1/collections/documents/search")).toHaveLength(0);
  });
});

describe("Search results", () => {
  it("shows each score with its score kind, the source and its availability", async () => {
    const { user } = setup();
    const items = within(await search(user)).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("0.8123");
    expect(items[0]).toHaveTextContent("Dense similarity (dense_similarity_v1)");
    expect(items[0]).toHaveTextContent("Present on this machine");
    expect(items[1]).toHaveTextContent("Reciprocal rank fusion (rrf_v1)");
    expect(items[1]).toHaveTextContent("Missing on this machine");
    // Server text is shown as text, never as markup.
    expect(items[1]).toHaveTextContent("<b>not markup</b>");
    expect(items[1]?.querySelector("b")).toBeNull();
    expect(items[2]).toHaveTextContent("Not ranked: neighbour context");
    expect(items[2]).toHaveTextContent("Unknown on this machine");
  });

  it("opens the stored chunk and navigates to its neighbours", async () => {
    const { server, user } = setup();
    const results = await search(user);
    await user.click(within(results).getAllByRole("button", { name: "Show chunk" })[0]!);

    const viewer = await screen.findByRole("region", { name: "Stored chunk" });
    expect(await within(viewer).findByText("Second chunk")).toBeInTheDocument();
    expect(within(viewer).getByText(/Chunk 3 of 4/)).toBeInTheDocument();
    expect(server.find("GET", "/v1/collections/documents/chunks/c-2")[0]?.path).toBe("/v1/collections/documents/chunks/c-2?window=1");

    await user.click(within(viewer).getByRole("button", { name: "Next chunk" }));
    expect(await within(viewer).findByText("Third chunk")).toBeInTheDocument();
    expect(within(viewer).getByRole("button", { name: "Next chunk" })).toBeDisabled();
    expect(within(viewer).getByRole("button", { name: "Previous chunk" })).toBeEnabled();
  });

  it("offers no chunk link for a legacy row without a chunk id", async () => {
    const { user } = setup();
    const items = within(await search(user)).getAllByRole("listitem");
    expect(within(items[2]!).queryByRole("button", { name: "Show chunk" })).not.toBeInTheDocument();
    expect(items[2]).toHaveTextContent("No stored chunk ID");
  });
});
