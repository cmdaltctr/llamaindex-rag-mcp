import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { documentsServer, type Handler } from "../test/fakeDocumentsServer";
import { fakeChats } from "../test/fakeChats";
import { startApp } from "../test/startApp";

const USAGE = { input_tokens: 1240, output_tokens: 380, reasoning_tokens: 210, cost_usd: 0.0012, calls: 2 };

function answer(overrides: Record<string, unknown> = {}) {
  return {
    status: "ok", query: "q", answer: "Lineage is kept.", citations: [], evidence: [],
    failure_stage: null, error: null, completion_source: "server", ...overrides,
  };
}

function setup(handlers: Record<string, Handler> = {}, seed: Parameters<typeof fakeChats>[0] = {}, hash = "#/chat/documents") {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  const store = fakeChats(seed);
  const server = documentsServer({
    "POST /v1/collections/documents/answer": () => answer({ reasoning: "First I read [1].\nThen I wrote.", usage: USAGE }),
    "GET /v1/usage/credit": () => ({ status: "ok", available: false }),
    ...store.handlers,
    ...handlers,
  });
  startApp(hash, server);
  return { server, user: userEvent.setup() };
}

async function ask(user: ReturnType<typeof userEvent.setup>, question = "What is kept?") {
  await user.type(await screen.findByRole("textbox", { name: "Question" }), question);
  await user.click(screen.getByRole("button", { name: "Send" }));
}

const credits = (server: ReturnType<typeof setup>["server"]) => server.exact("GET", "/v1/usage/credit").length;

describe("reasoning box", () => {
  it("shows a collapsed Reasoning control above the answer and hides the text until opened", async () => {
    const { user } = setup();
    await ask(user);
    const answerText = await screen.findByText("Lineage is kept.");
    const control = screen.getByRole("button", { name: "Reasoning" });
    expect(control).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/First I read/)).toBeNull();
    expect(control.compareDocumentPosition(answerText) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await user.click(control);
    expect(control).toHaveAttribute("aria-expanded", "true");
    const text = screen.getByText(/First I read/);
    expect(text).toHaveClass("text-meta", "text-muted-foreground");
    expect(text).toHaveTextContent("First I read [1]. Then I wrote.");
    expect(within(text).queryByRole("button")).toBeNull();
  });

  it("opens with Enter from the keyboard and reports the open state", async () => {
    const { user } = setup();
    await ask(user);
    const control = await screen.findByRole("button", { name: "Reasoning" });
    control.focus();
    await user.keyboard("{Enter}");
    expect(control).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/First I read/)).toBeVisible();
  });

  it("shows no Reasoning control for a turn saved before the change", async () => {
    setup({}, { chats: [{ chat_id: "old-1", folder_id: null, title: "Old", turns: [{ position: 1, collection: "documents", question: "Old question", answer: answer({ answer: "A saved answer." }) as never, created_at: "t" }] }] }, "#/chat/documents/old-1");
    expect(await screen.findByText("A saved answer.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reasoning" })).toBeNull();
  });
});

describe("usage line", () => {
  it("shows the tokens and cost of the latest answer above the question box", async () => {
    const { user } = setup();
    await ask(user);
    const line = await screen.findByTestId("usage-line");
    expect(line).toHaveTextContent(/^1,240 in · 380 out · 210 reasoning · \$0\.0012$/);
    expect(line).toHaveClass("text-meta", "text-muted-foreground", "truncate");
  });

  it("leaves out the dollar figure when the cost is unknown", async () => {
    const { user } = setup({ "POST /v1/collections/documents/answer": () => answer({ usage: { ...USAGE, cost_usd: null, reasoning_tokens: null } }) });
    await ask(user);
    const line = await screen.findByTestId("usage-line");
    expect(line).toHaveTextContent(/^1,240 in · 380 out$/);
    expect(line.textContent).not.toContain("$");
  });

  it("ends with the remaining credit when the provider reports it", async () => {
    const { user } = setup({ "GET /v1/usage/credit": () => ({ status: "ok", available: true, limit_usd: 10, remaining_usd: 2.81 }) });
    await ask(user);
    await waitFor(() => expect(screen.getByTestId("usage-line")).toHaveTextContent(/ · \$2\.81 left$/));
  });

  it("shows nothing when the latest answer has no usage, and sends no credit request", async () => {
    const { user, server } = setup({ "POST /v1/collections/documents/answer": () => answer() });
    await ask(user);
    await screen.findByText("Lineage is kept.");
    expect(screen.queryByTestId("usage-line")).toBeNull();
    expect(credits(server)).toBe(0);
  });

  it("shows the full figures and the number of calls on focus", async () => {
    const { user } = setup();
    await ask(user);
    const line = await screen.findByTestId("usage-line");
    line.focus();
    const tip = await screen.findByRole("tooltip");
    expect(tip).toHaveTextContent("Model calls: 2");
    expect(tip).toHaveTextContent("Input tokens: 1,240");
    expect(tip).toHaveTextContent("Reasoning tokens: 210");
  });

  it("reads the credit once per finished answer and never while the user types", async () => {
    const { user, server } = setup({ "GET /v1/usage/credit": () => ({ status: "ok", available: true, limit_usd: 10, remaining_usd: 2.81 }) });
    await ask(user);
    await waitFor(() => expect(screen.getByTestId("usage-line")).toHaveTextContent("left"));
    expect(credits(server)).toBe(1);
    await user.type(screen.getByRole("textbox", { name: "Question" }), "A long next question");
    expect(credits(server)).toBe(1);
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(screen.getAllByText("Lineage is kept.")).toHaveLength(2));
    await waitFor(() => expect(credits(server)).toBe(2));
    await user.type(screen.getByRole("textbox", { name: "Question" }), "more");
    expect(credits(server)).toBe(2);
  });
});
