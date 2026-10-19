import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeChats } from "../test/fakeChats";
import { documentsServer, type Handler } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

function evidence(ordinal: number, file: string, text: string) {
  return {
    ordinal, chunk_id: `c-${ordinal}`, chunk_ids: [`c-${ordinal}`], source_id: `sid-${ordinal}`, source_version: "v1",
    source: `/srv/docs/${file}`, source_chunk_index: ordinal, score: 0.5, score_kind: "reranker_sigmoid_v1", text,
  };
}

function cited(ordinal: number, file: string) {
  const { text, ...rest } = evidence(ordinal, file, "");
  void text;
  return rest;
}

function answer(files: string[], text = "Lineage is kept [1].") {
  return {
    status: "ok", query: "q", answer: text,
    citations: files.map((file, index) => cited(index + 1, file)),
    evidence: files.map((file, index) => evidence(index + 1, file, `Text of ${file}`)),
    failure_stage: null, error: null, completion_source: "server",
  };
}

function setup(handlers: Record<string, Handler> = {}, hash = "#/chat/documents", seed = {}) {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  const store = fakeChats(seed);
  startApp(hash, documentsServer({ "POST /v1/collections/documents/answer": () => answer(["one.md", "two.md"]), ...store.handlers, ...handlers }));
  return userEvent.setup();
}

async function ask(user: ReturnType<typeof userEvent.setup>, question = "What is kept?") {
  await user.type(await screen.findByRole("textbox", { name: "Question" }), question);
  await user.click(screen.getByRole("button", { name: "Send" }));
}

const panel = async () => within(await screen.findByRole("complementary", { name: "Knowledge base panel" }));

describe("icon tabs in the right-hand card", () => {
  it("offers Knowledge base, Citations and Evidence as tabs, with Knowledge base first", async () => {
    setup();
    const card = await panel();
    const tabs = card.getAllByRole("tab");
    expect(tabs.map((tab) => tab.getAttribute("aria-label"))).toEqual(["Knowledge base", "Citations", "Evidence"]);
    expect(tabs.map((tab) => tab.textContent?.trim())).toEqual(["", "", ""]);
    expect(card.getByRole("tab", { name: "Knowledge base" })).toHaveAttribute("aria-selected", "true");
    expect(await card.findByRole("list", { name: "Knowledge bases" })).toBeInTheDocument();
  });

  it("says nothing has been answered yet on the Citations and Evidence tabs", async () => {
    const user = setup();
    const card = await panel();
    await user.click(await card.findByRole("tab", { name: "Citations" }));
    expect(card.getByText("Citations of the latest answer appear here.")).toBeInTheDocument();
    await user.click(card.getByRole("tab", { name: "Evidence" }));
    expect(card.getByText("Evidence of the latest answer appears here.")).toBeInTheDocument();
  });

  it("moves the citation chips out of the transcript and into the Citations tab", async () => {
    const user = setup();
    await ask(user);
    const transcript = await screen.findByRole("list", { name: "Transcript" });
    await within(transcript).findByText(/Lineage is kept/);
    expect(within(transcript).queryByRole("list", { name: "Citations" })).toBeNull();
    expect(within(transcript).queryByRole("button", { name: /Evidence/ })).toBeNull();
    const card = await panel();
    await user.click(card.getByRole("tab", { name: "Citations" }));
    const chips = await card.findByRole("list", { name: "Citations" });
    expect(within(chips).getAllByRole("button", { name: /^\[/ }).map((chip) => chip.textContent)).toEqual(["[1]one.md", "[2]two.md"]);
  });

  it("lists the evidence rows in the Evidence tab without a second toggle", async () => {
    const user = setup();
    await ask(user);
    await screen.findByText(/Lineage is kept/);
    const card = await panel();
    await user.click(card.getByRole("tab", { name: "Evidence" }));
    const rows = within(await card.findByRole("list", { name: "Evidence supplied to the model" })).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[1]).toHaveTextContent("/srv/docs/two.md");
    expect(rows[1]).toHaveTextContent("Reranker sigmoid (reranker_sigmoid_v1)");
    expect(within(rows[1]!).queryByText("Text of two.md")).toBeNull();
    expect(card.queryByRole("button", { name: /^Evidence \(/ })).toBeNull();
  });

  it("follows the latest answer", async () => {
    let calls = 0;
    const user = setup({ "POST /v1/collections/documents/answer": () => (calls++ === 0 ? answer(["first.md"]) : answer(["second.md", "third.md"], "Newer [1].")) });
    await ask(user, "First?");
    await screen.findByText(/Lineage is kept/);
    await ask(user, "Second?");
    await screen.findByText(/Newer/);
    const card = await panel();
    await user.click(card.getByRole("tab", { name: "Citations" }));
    const chips = await card.findByRole("list", { name: "Citations" });
    expect(within(chips).getAllByRole("button", { name: /^\[/ }).map((chip) => chip.textContent)).toEqual(["[1]second.md", "[2]third.md"]);
  });

  it("shows the citations of a reopened chat's last saved answer", async () => {
    const stored = {
      chat_id: "stored-1", folder_id: null, title: "Stored question",
      turns: [{ position: 1, collection: "documents", question: "Stored question", answer: answer(["saved.md"], "A saved answer [1]."), created_at: "t" }],
    };
    const user = setup({}, "#/chat/documents/stored-1", { chats: [stored] });
    await screen.findByText(/A saved answer/);
    const card = await panel();
    await user.click(card.getByRole("tab", { name: "Citations" }));
    expect(within(await card.findByRole("list", { name: "Citations" })).getAllByRole("button", { name: /^\[/ }).map((chip) => chip.textContent)).toEqual(["[1]saved.md"]);
  });

  it("puts a lineage and metadata button next to each citation chip", async () => {
    const user = setup();
    await ask(user);
    await screen.findByText(/Lineage is kept/);
    const card = await panel();
    await user.click(card.getByRole("tab", { name: "Citations" }));
    const chips = await card.findByRole("list", { name: "Citations" });
    expect(within(chips).getAllByRole("button", { name: /^Lineage and metadata of citation / })).toHaveLength(2);
    await user.click(within(chips).getByRole("button", { name: "Lineage and metadata of citation 2" }));
    expect(await screen.findByRole("region", { name: "Lineage" })).toBeInTheDocument();
  });
});
