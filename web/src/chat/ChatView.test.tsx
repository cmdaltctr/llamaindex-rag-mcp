import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PREFERENCES_KEY } from "../lib/preferences";
import { documentsServer, json, type Handler } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

function evidence(ordinal: number, chunkId: string | null, text: string) {
  return {
    ordinal, chunk_id: chunkId, chunk_ids: chunkId ? [chunkId] : [], source_id: "sid-present", source_version: "v1",
    source: "/srv/docs/present.md", source_chunk_index: ordinal, score: 0.5, score_kind: "reranker_sigmoid_v1", text,
  };
}

function citation(ordinal: number, chunkId: string | null) {
  const { text, ...rest } = evidence(ordinal, chunkId, "");
  void text;
  return rest;
}

function answer(overrides: Record<string, unknown> = {}) {
  return {
    status: "ok", query: "q", answer: "Lineage is kept [1].",
    citations: [citation(1, "c-1"), citation(2, "c-2")],
    evidence: [evidence(1, "c-1", "Evidence one"), evidence(2, "c-2", "Evidence two")],
    failure_stage: null, error: null, completion_source: "server",
    ...overrides,
  };
}

const CHUNK = {
  status: "ok", collection: "documents", text_format: "plain",
  chunk: { chunk_id: "c-1", source_id: "sid-present", source_version: "v1", source_chunk_index: 1, source_chunk_count: 3, source: "/srv/docs/present.md", page_label: "4", text: "Stored chunk one", metadata: {} },
  previous: [], next: [],
};

function setup(handlers: Record<string, Handler> = {}, hash = "#/chat/documents") {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  const { server } = startApp(
    hash,
    documentsServer({
      "POST /v1/collections/documents/answer": () => answer(),
      "GET /v1/collections/documents/chunks/c-1": () => CHUNK,
      ...handlers,
    }),
  );
  return { server, user: userEvent.setup() };
}

async function ask(user: ReturnType<typeof userEvent.setup>, question = "What is kept?") {
  await user.type(await screen.findByRole("textbox", { name: "Question" }), question);
  await user.click(screen.getByRole("button", { name: "Send" }));
}

/** Opens a tab of the right-hand card. */
async function openTab(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(await screen.findByRole("tab", { name }));
}

function transcript() {
  return screen.getByRole("list", { name: "Transcript" });
}

describe("layout and routes", () => {
  it("shows the transcript column, the standalone notice, the composer and the knowledge base panel", async () => {
    setup();
    expect(await screen.findByRole("textbox", { name: "Question" })).toBeInTheDocument();
    expect(screen.getByText(/each question answers from the knowledge base on its own/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New chat" })).toBeInTheDocument();
    const panel = screen.getByRole("list", { name: "Knowledge bases" });
    const chips = within(panel).getAllByRole("button").filter((button) => button.hasAttribute("aria-pressed"));
    expect(chips[0]).toHaveTextContent("documents");
    expect(chips[0]).toHaveTextContent("3 documents, 12 chunks");
    expect(chips[0]).toHaveAttribute("aria-pressed", "true");
    expect(chips[1]).toHaveTextContent("notes");
    expect(chips[1]).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("chat-column").className).toContain("max-w-[48rem]");
  });

  it("docks the composer at the bottom of a column that fills the screen", async () => {
    setup();
    const field = await screen.findByRole("textbox", { name: "Question" });
    const composer = field.closest("form")!;
    const column = screen.getByTestId("chat-column");
    // The composer ends the column, the column fills the remaining height, and
    // the composer stays at the bottom edge while a long transcript scrolls.
    expect(column.lastElementChild).toBe(composer);
    expect(column).toHaveClass("flex", "flex-col", "flex-1");
    expect(composer).toHaveClass("mt-auto", "sticky", "bottom-0");
    let node: HTMLElement | null = column.parentElement;
    while (node !== null && node.tagName !== "MAIN") {
      expect(node, node.className).toHaveClass("flex-1");
      node = node.parentElement;
    }
    expect(node).toHaveClass("flex", "flex-col");
  });

  it("puts the knowledge base panel above the chat on small screens, so the composer ends the page", async () => {
    setup();
    await screen.findByRole("textbox", { name: "Question" });
    expect(screen.getByRole("complementary", { name: "Knowledge base panel" })).toHaveClass("order-first", "lg:order-none");
  });

  it("asks the user to choose when no collection is named and none is remembered", async () => {
    setup({}, "#/chat");
    expect(await screen.findByText(/choose a knowledge base/i)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Question" })).not.toBeInTheDocument();
    expect(window.location.hash).toBe("#/chat");
  });

  it("selects the last-used collection when the server still lists it", async () => {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ theme: "system", lastCollection: "notes" }));
    setup({}, "#/chat");
    expect(await screen.findByRole("textbox", { name: "Question" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/chat/notes");
  });

  it("drops a last-used collection that was deleted", async () => {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ theme: "system", lastCollection: "gone" }));
    setup({}, "#/chat");
    await screen.findByText(/choose a knowledge base/i);
    await waitFor(() => expect(JSON.parse(window.localStorage.getItem(PREFERENCES_KEY) ?? "{}").lastCollection).toBeNull());
  });

  it("shows not-found with a link to #/chat for an unknown collection", async () => {
    setup({}, "#/chat/missing");
    expect(await screen.findByText(/collection .missing. could not be found/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose a knowledge base" })).toHaveAttribute("href", "#/chat");
  });

  it("shows a friendly failure with Retry when the listing fails", async () => {
    setup({ "GET /v1/collections": () => json({ message: "Unexpected token <" }, 500) });
    const alert = await screen.findByRole("alert");
    expect(alert).not.toHaveTextContent("Unexpected token");
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("turns", () => {
  it("appends the user message then the assistant answer, queried with the question text", async () => {
    const { server, user } = setup();
    await ask(user);
    const items = await waitFor(() => {
      const found = within(transcript()).getAllByRole("listitem");
      expect(found.length).toBeGreaterThanOrEqual(2);
      return found;
    });
    expect(items[0]).toHaveTextContent("You");
    expect(items[0]).toHaveTextContent("What is kept?");
    expect(await within(transcript()).findByText(/Lineage is kept/)).toBeInTheDocument();
    expect(server.find("POST", "/v1/collections/documents/answer")[0]?.body).toEqual({
      query: "What is kept?", top_k: null, rerank: null, hybrid: null, metadata_filter: null,
    });
    expect(screen.getByRole("textbox", { name: "Question" })).toHaveValue("");
  });

  it("disables the composer and shows pending text while a turn waits", async () => {
    let release: (value: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => (release = resolve));
    const { user } = setup({ "POST /v1/collections/documents/answer": () => pending });
    await ask(user);
    expect(await screen.findByText(/waiting for the answer/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await act(async () => release(json(answer())));
    expect(await screen.findByText(/Lineage is kept/)).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Question" }), "again");
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  it("shows status as text under the answer, and the citation chips and evidence in the panel tabs", async () => {
    const { user } = setup({ "POST /v1/collections/documents/answer": () => answer({ verified: true }) });
    await ask(user);
    const turn = (await within(transcript()).findByText(/Lineage is kept/)).closest("li") as HTMLElement;
    expect(within(turn).getByText("Cited and verified")).toHaveAttribute("data-slot", "badge");
    expect(within(turn).queryByRole("list", { name: "Citations" })).not.toBeInTheDocument();
    await openTab(user, "Citations");
    const chips = await screen.findByRole("list", { name: "Citations" });
    expect(within(chips).getAllByRole("button", { name: /^\[/ })).toHaveLength(2);
    await openTab(user, "Evidence");
    const rows = within(await screen.findByRole("list", { name: "Evidence supplied to the model" })).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[1]).toHaveTextContent("/srv/docs/present.md");
    expect(rows[1]).not.toHaveTextContent("Evidence two");
    expect(rows[1]).toHaveTextContent("Reranker sigmoid (reranker_sigmoid_v1)");
  });

  it("opens a citation chip in a popover, then the full chunk in the chunk viewer", async () => {
    const { user } = setup();
    await ask(user);
    await screen.findByText(/Lineage is kept/);
    await openTab(user, "Citations");
    const chips = await screen.findByRole("list", { name: "Citations" });
    await user.click(within(chips).getByRole("button", { name: /\[1\]/ }));
    expect(await screen.findByText("Evidence one", { selector: "[data-slot='citation-popover-content'] *" })).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Open full chunk" }));
    const viewer = await screen.findByRole("dialog", { name: "Stored chunk" });
    expect(await within(viewer).findByText("Stored chunk one")).toBeInTheDocument();
    expect(within(viewer).getByText(/Page 4/)).toBeInTheDocument();
  });

  it("shows no passage text in an evidence row until Show passage is pressed", async () => {
    const { user } = setup();
    await ask(user);
    await screen.findByText(/Lineage is kept/);
    await openTab(user, "Evidence");
    const rows = within(await screen.findByRole("list", { name: "Evidence supplied to the model" })).getAllByRole("listitem");
    expect(rows[0]).not.toHaveTextContent("Evidence one");
    expect(within(rows[0]!).queryByRole("button", { name: /Show chunk/ })).toBeNull();
    await user.click(within(rows[0]!).getByRole("button", { name: "Show passage for evidence 1" }));
    expect(await screen.findByText("Evidence one", { selector: "[data-slot='citation-popover-content'] *" })).toBeInTheDocument();
    expect(rows[0]).not.toHaveTextContent("Evidence one");
  });

  it("opens an evidence passage in a popover, then the full chunk in the chunk viewer", async () => {
    const { user } = setup();
    await ask(user);
    await screen.findByText(/Lineage is kept/);
    await openTab(user, "Evidence");
    await user.click(await screen.findByRole("button", { name: "Show passage for evidence 1" }));
    expect(await screen.findByText("Evidence one", { selector: "[data-slot='citation-popover-content'] *" })).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Open full chunk" }));
    const viewer = await screen.findByRole("dialog", { name: "Stored chunk" });
    expect(await within(viewer).findByText("Stored chunk one")).toBeInTheDocument();
  });

  it("does not offer a chunk link for a citation without a stored chunk id", async () => {
    const { user } = setup({ "POST /v1/collections/documents/answer": () => answer({ citations: [citation(1, null)], evidence: [] }) });
    await ask(user);
    await screen.findByText(/Lineage is kept/);
    await openTab(user, "Citations");
    const chips = await screen.findByRole("list", { name: "Citations" });
    expect(within(chips).queryByRole("button")).not.toBeInTheDocument();
    expect(chips).toHaveTextContent("No stored chunk ID");
  });

  it.each([
    [{}, "Cited", /at least one valid citation/],
    [{ status: "no_evidence", answer: null, citations: [], evidence: [] }, "No evidence", /No model was called/],
    [{ status: "generation_unverified", citations: [] }, "Unverified answer", /no valid citation/],
    [{ status: "unverified_claims", unverified_claims: [{ claim: "Lineage is optional", verdict: "unsupported", ordinals: [1] }] }, "Unverified claims", /does not support/],
  ])("labels status %j with its real meaning", async (overrides, label, meaning) => {
    const { user } = setup({ "POST /v1/collections/documents/answer": () => answer(overrides) });
    await ask(user);
    const badge = await screen.findByText(label, { selector: "[data-slot=badge]" });
    expect(badge.closest("li")).toHaveTextContent(meaning);
  });

  it("lists claims that failed verification and why verification was skipped", async () => {
    const { user } = setup({
      "POST /v1/collections/documents/answer": () =>
        answer({ status: "unverified_claims", unverified_claims: [{ claim: "Lineage is optional", verdict: "unsupported", ordinals: [1] }], verification_skipped: "judge provider unavailable" }),
    });
    await ask(user);
    expect(await screen.findByRole("list", { name: "Claims that failed verification" })).toHaveTextContent("Lineage is optional (unsupported, cites [1])");
    expect(screen.getByText(/Claim verification skipped: judge provider unavailable/)).toBeInTheDocument();
  });
});

describe("failed turns", () => {
  it("shows one friendly line and Retry for an error status, with the raw message in the console only", async () => {
    let calls = 0;
    const { user } = setup({
      "POST /v1/collections/documents/answer": () =>
        ++calls === 1 ? answer({ status: "error", answer: null, citations: [], evidence: [], failure_stage: "retrieval", error: "Traceback: Store <html>offline" }) : answer(),
    });
    await ask(user);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/could not search/i);
    expect(alert).not.toHaveTextContent("Traceback");
    expect(alert).not.toHaveTextContent("<html>");
    expect(console.error).toHaveBeenCalledWith(expect.stringContaining("Traceback"), expect.anything());
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/Lineage is kept/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    // Retry replaces the failed turn; it does not add another question.
    expect(within(transcript()).getAllByText("What is kept?")).toHaveLength(1);
  });

  it("shows one friendly line and Retry for a transport failure", async () => {
    const { user } = setup({ "POST /v1/collections/documents/answer": () => json({ status: "error", message: "Unexpected token <" }, 500) });
    await ask(user);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(alert).not.toHaveTextContent("Unexpected token");
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("knowledge base panel and New chat", () => {
  it("rewrites the route and the last-used collection, keeps earlier turns and queries the new collection", async () => {
    const { server, user } = setup({
      "POST /v1/collections/notes/answer": () => answer({ answer: "From notes." }),
    });
    await ask(user, "first");
    await screen.findByText(/Lineage is kept/);
    await ask(user, "second");
    await waitFor(() => expect(within(transcript()).getAllByText(/Lineage is kept/)).toHaveLength(2));

    await user.click(within(screen.getByRole("list", { name: "Knowledge bases" })).getByRole("button", { name: /^notes/ }));
    expect(window.location.hash).toBe("#/chat/notes");
    expect(JSON.parse(window.localStorage.getItem(PREFERENCES_KEY) ?? "{}").lastCollection).toBe("notes");
    expect(within(transcript()).getAllByText(/Lineage is kept/)).toHaveLength(2);

    await ask(user, "third");
    expect(await screen.findByText("From notes.")).toBeInTheDocument();
    expect(server.find("POST", "/v1/collections/notes/answer")).toHaveLength(1);
    expect(server.find("POST", "/v1/collections/documents/answer")).toHaveLength(2);
    expect(within(transcript()).getByText("first")).toBeInTheDocument();
  });

  it("clears the transcript with New chat and keeps the selected knowledge base", async () => {
    const { user } = setup();
    await ask(user);
    await screen.findByText(/Lineage is kept/);
    await user.click(screen.getByRole("button", { name: "New chat" }));
    expect(screen.queryByRole("list", { name: "Transcript" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Lineage is kept/)).not.toBeInTheDocument();
    expect(window.location.hash).toBe("#/chat/documents");
    expect(screen.getByRole("textbox", { name: "Question" })).toBeInTheDocument();
  });

  it("shows the display name in the picker and keeps the collection name in the question box", async () => {
    const collections = [
      { name: "documents", document_count: 3, chunk_count: 12, profile: null, display_name: "Project docs", store: { name: "lancedb", label: "LanceDB" } },
      { name: "notes", document_count: 1, chunk_count: 2, profile: null, display_name: null, store: { name: "lancedb", label: "LanceDB" } },
    ];
    startApp("#/chat/documents", documentsServer({ "GET /v1/collections": () => collections }));
    const picker = await screen.findByRole("list", { name: "Knowledge bases" });
    const buttons = within(picker).getAllByRole("button").filter((button) => button.hasAttribute("aria-pressed"));
    expect(buttons[0]).toHaveTextContent("Project docs");
    expect(buttons[1]).toHaveTextContent("notes");
    expect(await screen.findByPlaceholderText("Ask documents a question")).toBeInTheDocument();
  });
});

describe("Chat model status", () => {
  const NOT_READY = { status: "ok", provider: null, model: null, source: "default", locked: false, lock_reason: null, enabled: true, ready: false, reason: "not-configured" };

  it("shows one line with a link to the Chat settings and disables Send when no model is connected", async () => {
    const { user } = setup({ "GET /v1/settings/chat": () => NOT_READY });
    const field = await screen.findByRole("textbox", { name: "Question" });
    const notice = await screen.findByRole("alert");
    expect(notice).toHaveTextContent("Chat has no model connected.");
    expect(within(notice).getByRole("link", { name: "Connect a model" })).toHaveAttribute("href", "#/settings/chat");
    await user.type(field, "What is kept?");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("says answering is turned off for the reason disabled, with no server text", async () => {
    setup({ "GET /v1/settings/chat": () => ({ ...NOT_READY, enabled: false, reason: "disabled", detail: "ANSWER__ENABLED=false in /srv/.env" }) });
    const notice = await screen.findByRole("alert");
    expect(notice).toHaveTextContent("Answering is turned off on the server.");
    expect(document.body.textContent).not.toContain("/srv/.env");
  });

  it("shows no notice and enables Send when Chat is ready", async () => {
    const { user } = setup();
    await user.type(await screen.findByRole("textbox", { name: "Question" }), "q");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  it("puts the settings link beside Retry when an answer fails at the generation stage", async () => {
    const { user } = setup({
      "POST /v1/collections/documents/answer": () => answer({ status: "error", answer: null, citations: [], evidence: [], failure_stage: "generation", error: "401 from provider at /srv/x" }),
    });
    await ask(user);
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(within(alert).getByRole("link", { name: "Check the Chat model" })).toHaveAttribute("href", "#/settings/chat");
    expect(alert).not.toHaveTextContent("/srv/x");
  });

  it("gives a retrieval failure no settings link", async () => {
    const { user } = setup({
      "POST /v1/collections/documents/answer": () => answer({ status: "error", answer: null, citations: [], evidence: [], failure_stage: "retrieval", error: "offline" }),
    });
    await ask(user);
    const alert = await screen.findByRole("alert");
    expect(within(alert).queryByRole("link")).toBeNull();
  });
});
