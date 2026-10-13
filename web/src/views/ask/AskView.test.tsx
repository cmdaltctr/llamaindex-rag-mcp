import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { documentsServer } from "../test/fakeDocumentsServer";
import { AskView } from "./AskView";

function evidence(ordinal: number, chunkId: string | null, text: string) {
  return {
    ordinal, chunk_id: chunkId, chunk_ids: chunkId ? [chunkId] : [], source_id: "sid-present", source_version: "v1",
    source: "/srv/docs/present.md", source_chunk_index: ordinal, score: 0.5, score_kind: "reranker_sigmoid_v1", text,
  };
}

function citation(ordinal: number, chunkId: string | null) {
  const { text: _text, ...rest } = evidence(ordinal, chunkId, "");
  void _text;
  return rest;
}

function result(overrides: Record<string, unknown>) {
  return {
    status: "ok",
    query: "q",
    answer: "Lineage is kept [1]. Unsupported marker [7].",
    citations: [citation(1, "c-1")],
    evidence: [evidence(1, "c-1", "Evidence one"), evidence(2, "c-2", "Evidence two")],
    failure_stage: null,
    error: null,
    completion_source: "server",
    ...overrides,
  };
}

function setup(answer: Record<string, unknown>) {
  const server = documentsServer({
    "POST /v1/collections/documents/answer": () => answer,
    "GET /v1/collections/documents/chunks/c-1": () => ({
      status: "ok", collection: "documents", text_format: "plain",
      chunk: { chunk_id: "c-1", source_id: "sid-present", source_version: "v1", source_chunk_index: 1, source_chunk_count: 3, source: "/srv/docs/present.md", page_label: "4", text: "Stored chunk one", metadata: {} },
      previous: [], next: [],
    }),
  });
  render(<AskView fetchImpl={server.fetchImpl} />);
  return { server, user: userEvent.setup() };
}

async function ask(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole("option", { name: "documents" });
  await user.type(screen.getByRole("textbox", { name: "Question" }), "What is kept?");
  await user.click(screen.getByRole("button", { name: "Ask" }));
  return screen.findByRole("region", { name: "Answer" });
}

describe("Ask", () => {
  it("sends the question with profile-resolved controls", async () => {
    const { server, user } = setup(result({}));
    await ask(user);
    expect(server.find("POST", "/v1/collections/documents/answer")[0]?.body).toEqual({
      query: "What is kept?", top_k: null, rerank: null, hybrid: null, metadata_filter: null,
    });
  });

  it("links only the server's citations to stored chunks and never invents one", async () => {
    const { user } = setup(result({}));
    const answer = await ask(user);
    expect(within(answer).getByText("Lineage is kept [1]. Unsupported marker [7].")).toBeInTheDocument();
    const citations = within(answer).getByRole("list", { name: "Citations" });
    expect(within(citations).getAllByRole("listitem")).toHaveLength(1);
    expect(within(citations).getByText(/\[1\]/)).toBeInTheDocument();
    expect(within(answer).queryByText(/\[7\].*present\.md/)).not.toBeInTheDocument();

    await user.click(within(citations).getByRole("button", { name: "Show chunk for citation 1" }));
    const viewer = await screen.findByRole("region", { name: "Stored chunk" });
    expect(await within(viewer).findByText("Stored chunk one")).toBeInTheDocument();
    expect(within(viewer).getByText(/Page 4/)).toBeInTheDocument();
  });

  it("shows supplied evidence separately from citations", async () => {
    const { user } = setup(result({}));
    const answer = await ask(user);
    const items = within(within(answer).getByRole("list", { name: "Evidence supplied to the model" })).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[1]).toHaveTextContent("Evidence two");
    expect(items[1]).toHaveTextContent("Reranker sigmoid (reranker_sigmoid_v1)");
  });

  it("does not offer a chunk link for a citation without a stored chunk id", async () => {
    const { user } = setup(result({ citations: [citation(1, null)] }));
    const answer = await ask(user);
    const citations = within(answer).getByRole("list", { name: "Citations" });
    expect(within(citations).queryByRole("button")).not.toBeInTheDocument();
    expect(citations).toHaveTextContent("No stored chunk ID");
  });

  it.each([
    [{}, "Cited", /at least one valid citation/],
    [{ verified: true }, "Cited and verified", /Claim verification passed/],
    [{ status: "no_evidence", answer: null, citations: [], evidence: [] }, "No evidence", /No model was called/],
    [{ status: "generation_unverified", citations: [] }, "Unverified answer", /no valid citation/],
  ])("labels status %j with its real meaning", async (overrides, label, meaning) => {
    const { user } = setup(result(overrides));
    const answer = await ask(user);
    const status = within(answer).getByRole("status");
    expect(status).toHaveTextContent(label);
    expect(status).toHaveTextContent(meaning);
  });

  it("lists claims that failed verification", async () => {
    const { user } = setup(
      result({
        status: "unverified_claims",
        unverified_claims: [{ claim: "Lineage is optional", verdict: "unsupported", ordinals: [1] }],
      }),
    );
    const answer = await ask(user);
    expect(within(answer).getByRole("status")).toHaveTextContent("Unverified claims");
    expect(within(answer).getByRole("list", { name: "Claims that failed verification" })).toHaveTextContent(
      "Lineage is optional (unsupported, cites [1])",
    );
  });

  it("shows why claim verification was skipped and keeps the weaker guarantee", async () => {
    const { user } = setup(result({ verification_skipped: "judge provider unavailable" }));
    const answer = await ask(user);
    const status = within(answer).getByRole("status");
    expect(status).toHaveTextContent("Cited");
    expect(status).not.toHaveTextContent("verified");
    expect(within(answer).getByText(/Claim verification skipped: judge provider unavailable/)).toBeInTheDocument();
  });

  it("reports a failure with its stage", async () => {
    const { user } = setup(
      result({ status: "error", answer: null, citations: [], evidence: [], failure_stage: "retrieval", error: "Store offline." }),
    );
    const answer = await ask(user);
    const status = within(answer).getByRole("status");
    expect(status).toHaveTextContent("Failed during retrieval");
    expect(status).toHaveTextContent("Store offline.");
  });
});
