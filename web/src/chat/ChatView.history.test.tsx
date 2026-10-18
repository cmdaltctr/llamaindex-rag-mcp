import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { documentsServer, json, type Handler } from "../test/fakeDocumentsServer";
import { fakeChats, type FakeChatSeed } from "../test/fakeChats";
import { startApp } from "../test/startApp";

function answer(overrides: Record<string, unknown> = {}) {
  return {
    status: "ok", query: "q", answer: "Lineage is kept.", citations: [], evidence: [],
    failure_stage: null, error: null, completion_source: "server", ...overrides,
  };
}

function setup(seed: FakeChatSeed = {}, handlers: Record<string, Handler> = {}) {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  const store = fakeChats(seed);
  const server = documentsServer({
    "POST /v1/collections/documents/answer": () => answer(),
    ...store.handlers,
    ...handlers,
  });
  return { store, server, user: userEvent.setup() };
}

async function ask(user: ReturnType<typeof userEvent.setup>, question = "What is kept?") {
  await user.type(await screen.findByRole("textbox", { name: "Question" }), question);
  await user.click(screen.getByRole("button", { name: "Send" }));
}

const answers = (server: ReturnType<typeof setup>["server"]) => server.find("POST", "/v1/collections/documents/answer").length;
const turnPosts = (server: ReturnType<typeof setup>["server"]) => server.calls.filter((c) => c.method === "POST" && c.path.endsWith("/turns"));

describe("stored chats", () => {
  it("creates the chat on the first usable answer, then reloads it without asking again", async () => {
    const { store, server, user } = setup();
    startApp("#/chat/documents", server);
    await ask(user);
    expect(await screen.findByText("Lineage is kept.")).toBeInTheDocument();
    await waitFor(() => expect(store.chats.size).toBe(1));
    const [chat] = [...store.chats.values()];
    expect(chat!.title).toBe("What is kept?");
    await waitFor(() => expect(chat!.turns).toHaveLength(1));
    expect(chat!.turns[0]).toMatchObject({ collection: "documents", question: "What is kept?" });
    await waitFor(() => expect(window.location.hash).toBe(`#/chat/documents/${chat!.chat_id}`));

    cleanup();
    startApp(`#/chat/documents/${chat!.chat_id}`, server);
    expect(await screen.findByText("Lineage is kept.")).toBeInTheDocument();
    expect(screen.getByText("What is kept?")).toBeInTheDocument();
    expect(answers(server)).toBe(1);
  });

  it("saves each later answer into the same chat", async () => {
    const { store, server, user } = setup();
    startApp("#/chat/documents", server);
    await ask(user, "First?");
    await waitFor(() => expect([...store.chats.values()][0]?.turns).toHaveLength(1));
    await ask(user, "Second?");
    await waitFor(() => expect([...store.chats.values()][0]?.turns).toHaveLength(2));
    expect(store.chats.size).toBe(1);
  });

  it("does not save an error result, and saves the answer of a successful retry", async () => {
    let calls = 0;
    const { store, server, user } = setup({}, {
      "POST /v1/collections/documents/answer": () => {
        calls += 1;
        return calls === 1 ? answer({ status: "error", answer: null, failure_stage: "generation", error: "boom" }) : answer();
      },
    });
    startApp("#/chat/documents", server);
    await ask(user);
    await user.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Lineage is kept.")).toBeInTheDocument();
    await waitFor(() => expect(turnPosts(server)).toHaveLength(1));
    expect(calls).toBe(2);
    expect(store.chats.size).toBe(1);
  });

  it("saves nothing when the only answer is an error", async () => {
    const { store, server, user } = setup({}, {
      "POST /v1/collections/documents/answer": () => answer({ status: "error", answer: null, failure_stage: "generation", error: "boom" }),
    });
    startApp("#/chat/documents", server);
    await ask(user);
    await screen.findByRole("button", { name: "Retry" });
    expect(server.find("POST", "/v1/chats")).toHaveLength(0);
    expect(store.chats.size).toBe(0);
  });

  it("drops the turn without a notice when the chat was deleted while the answer was pending", async () => {
    const { store, server, user } = setup({ chats: [{ chat_id: "gone", folder_id: null, title: "Old" }] }, {
      "POST /v1/chats/:id/turns": () => json({ status: "error", message: "That chat or folder does not exist." }, 404),
    });
    startApp("#/chat/documents/gone", server);
    await ask(user);
    expect(await screen.findByText("Lineage is kept.")).toBeInTheDocument();
    await waitFor(() => expect(turnPosts(server)).toHaveLength(1));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(store.chats.get("gone")?.turns).toHaveLength(0);
  });

  it("shows a short notice and a new empty chat for an id the server does not know", async () => {
    const { server } = setup();
    startApp("#/chat/documents/nope", server);
    expect(await screen.findByText(/that chat is no longer stored/i)).toBeInTheDocument();
    expect(await screen.findByRole("textbox", { name: "Question" })).toBeInTheDocument();
    await waitFor(() => expect(window.location.hash).toBe("#/chat/documents"));
    expect(screen.queryByRole("list", { name: "Transcript" })).not.toBeInTheDocument();
  });
});

const STORED = {
  chat_id: "stored-1",
  folder_id: null,
  title: "Stored question",
  turns: [
    {
      position: 1,
      collection: "notes",
      question: "Stored question",
      answer: answer({ answer: "A saved answer." }) as never,
      created_at: "t",
    },
  ],
};

describe("history list in the view", () => {
  it("opens a stored chat in the collection of its last turn, without asking the model", async () => {
    const { server, user } = setup({ chats: [STORED] });
    startApp("#/chat/documents", server);
    await user.click(await screen.findByRole("button", { name: "Stored question" }));
    expect(await screen.findByText("A saved answer.")).toBeInTheDocument();
    await waitFor(() => expect(window.location.hash).toBe("#/chat/notes/stored-1"));
    expect(answers(server)).toBe(0);
    expect(server.find("POST", "/v1/collections/notes/answer")).toHaveLength(0);
  });

  it("keeps the open chat when another knowledge base is selected", async () => {
    const { server, user } = setup({ chats: [STORED] });
    startApp("#/chat/notes/stored-1", server);
    expect(await screen.findByText("A saved answer.")).toBeInTheDocument();
    const panel = screen.getByRole("list", { name: "Knowledge bases" });
    await user.click(within(panel).getByRole("button", { name: /documents/ }));
    await waitFor(() => expect(window.location.hash).toBe("#/chat/documents/stored-1"));
    expect(screen.getByText("A saved answer.")).toBeInTheDocument();
  });

  it("starts a new empty chat and keeps the old one in the history", async () => {
    const { server, user } = setup({ chats: [STORED] });
    startApp("#/chat/notes/stored-1", server);
    await screen.findByText("A saved answer.");
    await user.click(screen.getByRole("button", { name: "New chat" }));
    expect(screen.queryByText("A saved answer.")).not.toBeInTheDocument();
    expect(window.location.hash).toBe("#/chat/notes");
    expect(screen.getByRole("button", { name: "Stored question" })).toBeInTheDocument();
  });

  it("shows the history list behind a History button on narrow screens", async () => {
    const { server, user } = setup({ chats: [STORED] });
    startApp("#/chat/documents", server);
    const toggle = await screen.findByRole("button", { name: "History" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("complementary", { name: "Chat history" })).toHaveClass("hidden", "lg:flex");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("complementary", { name: "Chat history" })).not.toHaveClass("hidden");
  });
});

describe("deleting the open chat", () => {
  it("shows a new empty chat", async () => {
    const { server, user, store } = setup({ chats: [STORED] });
    startApp("#/chat/notes/stored-1", server);
    await screen.findByText("A saved answer.");
    await user.click(await screen.findByRole("button", { name: "Delete Stored question" }));
    await user.click(await screen.findByRole("button", { name: "Delete chat" }));
    await waitFor(() => expect(store.chats.size).toBe(0));
    await waitFor(() => expect(screen.queryByText("A saved answer.")).not.toBeInTheDocument());
    expect(window.location.hash).toBe("#/chat/notes");
  });
});

describe("review findings: loading and saving", () => {
  it("keeps the route and shows a retry line when a stored chat fails to load (not a 404)", async () => {
    const { server } = setup({}, { "GET /v1/chats/:id": () => json({ status: "error", message: "down" }, 503) });
    startApp("#/chat/documents/abc", server);
    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument();
    expect(screen.queryByText(/no longer stored/i)).not.toBeInTheDocument();
    expect(window.location.hash).toBe("#/chat/documents/abc");
  });

  it("does not reopen the old chat when New chat is pressed while the chat is still being created", async () => {
    let release: (value: Response) => void = () => undefined;
    const held = new Promise<Response>((resolve) => (release = resolve));
    const store = fakeChats();
    const { server, user } = setup({}, { "POST /v1/chats": async (body, call) => { const r = await held; void body; void call; return r; } });
    void store;
    startApp("#/chat/documents", server);
    await ask(user);
    expect(await screen.findByText(/Lineage is kept/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New chat" }));
    await act(async () => release(json({ status: "ok", chat: { chat_id: "late", folder_id: null, title: "t", created_at: "t", updated_at: "t" } }, 201)));
    await waitFor(() => expect(turnPosts(server)).toHaveLength(1));
    expect(turnPosts(server)[0]!.path).toBe("/v1/chats/late/turns");
    expect(window.location.hash).toBe("#/chat/documents");
    expect(screen.queryByText(/Lineage is kept/)).not.toBeInTheDocument();
  });

  it("saves answers in the order they arrived, even when the first save is slow", async () => {
    let release: (value: Response) => void = () => undefined;
    const held = new Promise<Response>((resolve) => (release = resolve));
    let first = true;
    const { store, server, user } = setup({}, {
      "POST /v1/chats/:id/turns": async (body, call) => {
        if (first) {
          first = false;
          await held;
        }
        const chat = store2.chats.get(call.path.split("/")[3]!)!;
        const position = chat.turns.length + 1;
        chat.turns.push({ position, collection: String(body.collection), question: String(body.question), answer: body.answer as never, created_at: "t" });
        return json({ status: "ok", turn: { chat_id: chat.chat_id, position, created_at: "t" } }, 201);
      },
    });
    const store2 = store;
    startApp("#/chat/documents", server);
    await ask(user, "First?");
    await waitFor(() => expect(turnPosts(server)).toHaveLength(1));
    await ask(user, "Second?");
    await screen.findAllByText(/Lineage is kept/);
    await new Promise((r) => setTimeout(r, 150));
    expect(turnPosts(server)).toHaveLength(1); // the second save waits for the first
    await act(async () => release(json({}, 200)));
    await waitFor(() => expect(turnPosts(server)).toHaveLength(2));
    await waitFor(() => expect([...store.chats.values()][0]?.turns.map((t) => t.question)).toEqual(["First?", "Second?"]));
  });
});

describe("review findings: knowledge base choice", () => {
  it("keeps a knowledge base picked while the first chat is being created", async () => {
    let release: (value: Response) => void = () => undefined;
    const held = new Promise<Response>((resolve) => (release = resolve));
    const { server, user } = setup({}, { "POST /v1/chats": async () => held });
    startApp("#/chat/documents", server);
    await ask(user);
    expect(await screen.findByText(/Lineage is kept/)).toBeInTheDocument();
    const panel = screen.getByRole("list", { name: "Knowledge bases" });
    await user.click(within(panel).getByRole("button", { name: /notes/ }));
    await waitFor(() => expect(window.location.hash).toBe("#/chat/notes"));
    await act(async () => release(json({ status: "ok", chat: { chat_id: "made", folder_id: null, title: "t", created_at: "t", updated_at: "t" } }, 201)));
    await waitFor(() => expect(window.location.hash).toBe("#/chat/notes/made"));
  });
});
