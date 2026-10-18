import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AnswerResult } from "../api/documents";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { AssistantTurn } from "./AssistantTurn";

function cite(ordinal: number, chunkIds: string[], source = "/srv/docs/paper.pdf") {
  return {
    ordinal, chunk_id: chunkIds[0] ?? null, chunk_ids: chunkIds, source_id: "sid-1", source_version: "v7",
    source, source_chunk_index: ordinal, score: 0.5, score_kind: "reranker_sigmoid_v1",
  };
}

const RESULT: AnswerResult = {
  status: "ok", query: "q", answer: "Lineage matters [1] and merges [2], not [7].",
  citations: [cite(1, ["c-1"]), cite(2, ["c-2", "c-3"])],
  evidence: [{ ...cite(1, ["c-1"]), text: "Evidence one" }, { ...cite(2, ["c-2", "c-3"]), text: "Evidence two" }],
  failure_stage: null, error: null, completion_source: "server",
} as AnswerResult;

function chunk(id: string, metadata: Record<string, unknown>) {
  return {
    status: "ok", collection: "documents", text_format: "plain",
    chunk: { chunk_id: id, source_id: "sid-1", source_version: "v7", source_chunk_index: 1, source_chunk_count: 5, source: "/srv/docs/paper.pdf", page_label: "4", text: "Stored", metadata },
    previous: [], next: [],
  };
}

function setup(handlers: Record<string, () => unknown> = {}) {
  const server = documentsServer({
    "GET /v1/collections/documents/chunks/c-1": () => chunk("c-1", { title: "A paper", file_name: "paper-copy.pdf" }),
    "GET /v1/collections/documents/chunks/c-2": () => chunk("c-2", { title: "A paper", keywords: ["rag"] }),
    ...handlers,
  });
  const onShowChunk = vi.fn();
  renderWithProviders(
    <ul>
      <AssistantTurn collection="documents" question="q" saved={RESULT} onShowChunk={onShowChunk} />
    </ul>,
    { fetchImpl: server.fetchImpl },
  );
  return { server, onShowChunk, user: userEvent.setup() };
}

const chip = (n: number) => within(screen.getByRole("list", { name: "Citations" })).getByRole("button", { name: new RegExp(`\\[${n}\\]`) });

describe("citation popover", () => {
  it("opens from a chip with the evidence, the lineage and the stored metadata", async () => {
    const { user } = setup();
    await user.click(chip(1));
    const panel = document.querySelector("[data-slot='citation-popover-content']") as HTMLElement;
    expect(within(panel).getByText("Evidence one")).toBeInTheDocument();
    expect(within(panel).getByText("paper.pdf")).toBeInTheDocument();
    expect(within(panel).getByText(/Score 0\.5000/)).toBeInTheDocument();
    expect(within(panel).getByRole("region", { name: "Lineage" })).toHaveTextContent("sid-1");
    const metadata = await within(panel).findByRole("region", { name: "Metadata" });
    expect(within(metadata).getByText("title")).toBeInTheDocument();
    expect(within(metadata).getByText("A paper")).toBeInTheDocument();
    expect(within(metadata).getByText("file_name")).toBeInTheDocument();
  });

  it("lists both chunk ids of a merged citation", async () => {
    const { user } = setup();
    await user.click(chip(2));
    const lineage = await screen.findByRole("region", { name: "Lineage" });
    expect(within(lineage).getByText("c-2, c-3")).toBeInTheDocument();
  });

  it("turns a [n] marker into a button only when it matches a citation", async () => {
    const { user } = setup();
    const answer = screen.getByText(/Lineage matters/);
    expect(within(answer).getByRole("button", { name: "Citation 1" })).toBeInTheDocument();
    expect(within(answer).getByRole("button", { name: "Citation 2" })).toBeInTheDocument();
    expect(within(answer).queryByRole("button", { name: "Citation 7" })).not.toBeInTheDocument();
    expect(answer).toHaveTextContent("not [7].");
    await user.click(within(answer).getByRole("button", { name: "Citation 1" }));
    expect(await screen.findByText("Evidence one")).toBeInTheDocument();
  });

  it("closes on Escape and returns focus to the chip", async () => {
    const { user } = setup();
    await user.click(chip(1));
    await screen.findByText("Evidence one", { selector: "[data-slot='citation-popover-content'] *" });
    await user.keyboard("{Escape}");
    expect(document.querySelector("[data-slot='citation-popover-content']")).toBeNull();
    expect(chip(1)).toHaveFocus();
  });

  it("keeps the saved evidence and says the chunk is gone when it is no longer stored", async () => {
    const { user } = setup({ "GET /v1/collections/documents/chunks/c-1": () => json({ status: "error", message: "gone" }, 404) as never });
    await user.click(chip(1));
    const panel = document.querySelector("[data-slot='citation-popover-content']") as HTMLElement;
    expect(await within(panel).findByText(/stored chunk is not available/i)).toBeInTheDocument();
    expect(within(panel).getByText("Evidence one")).toBeInTheDocument();
    expect(within(panel).queryByRole("region", { name: "Metadata" })).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("opens the full chunk from the popover", async () => {
    const { user, onShowChunk } = setup();
    await user.click(chip(1));
    await user.click(await screen.findByRole("button", { name: "Open full chunk" }));
    expect(onShowChunk).toHaveBeenCalledWith("documents", "c-1");
    await waitFor(() => expect(document.querySelector("[data-slot='citation-popover-content']")).toBeNull());
  });
});

describe("citation popover load failures", () => {
  it("shows a retry line, keeps Open full chunk and does not say the chunk is gone on a server error", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { user } = setup({ "GET /v1/collections/documents/chunks/c-1": () => json({ status: "error", message: "down" }, 503) as never });
    await user.click(chip(1));
    const panel = document.querySelector("[data-slot='citation-popover-content']") as HTMLElement;
    expect(await within(panel).findByRole("alert")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Open full chunk" })).toBeInTheDocument();
    expect(within(panel).queryByText(/stored chunk is not available/i)).not.toBeInTheDocument();
  });
});
