import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { CONFIG_DIR, CONNECTIONS, settingsServer } from "./test/fixtures";

async function openConnections(handlers = {}) {
  const server = settingsServer(handlers);
  startApp("#/settings", server);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Connections" }));
  await screen.findByRole("heading", { level: 3, name: "Ollama" });
  return { server, user };
}

function card(name: string) {
  return screen.getByRole("region", { name });
}

describe("Connections", () => {
  it("lists a card per provider with URLs, models, key state and role badges", async () => {
    await openConnections();
    expect(screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toEqual(["Ollama", "llama.cpp", "OpenRouter"]);

    const ollama = card("Ollama");
    expect(within(ollama).getByText("http://127.0.0.1:11434")).toBeInTheDocument();
    expect(within(ollama).getByText("llama3.2")).toBeInTheDocument();
    expect(within(ollama).getByText("No key")).toBeInTheDocument();
    expect(within(ollama).getByText("Answers")).toBeInTheDocument();
    expect(within(ollama).getByText("Metadata")).toBeInTheDocument();
    expect(within(ollama).queryByText("Embeddings")).toBeNull();

    const llamacpp = card("llama.cpp");
    expect(within(llamacpp).getByText("Embeddings")).toBeInTheDocument();
    expect(within(llamacpp).getAllByText(/127\.0\.0\.1:808/)).toHaveLength(2);

    expect(within(card("OpenRouter")).getByText("Key set")).toBeInTheDocument();
    expect(within(card("OpenRouter")).getByText("Verification")).toBeInTheDocument();
  });

  it("renders role labels as hue badges", async () => {
    await openConnections();
    const badge = within(card("llama.cpp")).getByText("Embeddings");
    expect(badge).toHaveAttribute("data-slot", "badge");
    expect(badge.style.getPropertyValue("--badge-hue")).not.toBe("");
  });

  it("says where the values come from and that a change needs a restart", async () => {
    await openConnections();
    const section = screen.getByRole("region", { name: "Connections" });
    const notice = within(section).getByText((_, element) => element?.tagName === "P" && /needs a server restart/i.test(element.textContent ?? ""));
    expect(notice).toHaveTextContent(`${CONFIG_DIR}/.env`);
    expect(within(notice).getByText(`${CONFIG_DIR}/.env`).tagName).toBe("CODE");
  });

  it("offers no edit control for connections", async () => {
    await openConnections();
    const section = screen.getByRole("region", { name: "Connections" });
    expect(within(section).queryAllByRole("textbox")).toHaveLength(0);
    expect(within(section).queryAllByRole("combobox")).toHaveLength(0);
    expect(within(section).queryAllByRole("switch")).toHaveLength(0);
    expect(within(section).getAllByRole("button").map((button) => button.textContent)).toEqual(["Test", "Test", "Test"]);
  });

  it("never shows a key value, even if the server sent extra fields", async () => {
    const leaky = { ...CONNECTIONS, connections: CONNECTIONS.connections.map((c) => ({ ...c, api_key: "sk-or-secret-123" })) };
    await openConnections({ "GET /v1/connections": () => leaky });
    expect(document.body.textContent).not.toContain("sk-or-secret-123");
  });

  it("sends no provider request until Test is pressed", async () => {
    const { server } = await openConnections();
    expect(server.calls.filter((call) => call.method === "POST")).toHaveLength(0);
    expect(server.calls.some((call) => call.path.includes("/test"))).toBe(false);
  });

  it("shows not reachable with the reason in text and a badge", async () => {
    const { user, server } = await openConnections({
      "POST /v1/connections/ollama/test": () => ({ status: "ok", reachable: false, reason: "refused" }),
    });
    await user.click(within(card("Ollama")).getByRole("button", { name: "Test" }));
    const result = await within(card("Ollama")).findByRole("status");
    expect(within(result).getByText("Not reachable")).toBeInTheDocument();
    expect(within(result).getByText("refused")).toHaveAttribute("data-slot", "badge");
    expect(result).toHaveTextContent(/connection was refused/i);
    expect(server.find("POST", "/v1/connections/")).toHaveLength(1);
  });

  it("shows reachable", async () => {
    const { user } = await openConnections({
      "POST /v1/connections/llamacpp/test": () => ({ status: "ok", reachable: true, reason: null }),
    });
    await user.click(within(card("llama.cpp")).getByRole("button", { name: "Test" }));
    expect(await within(card("llama.cpp")).findByText("Reachable")).toHaveAttribute("data-slot", "badge");
  });

  it.each([
    ["timeout", /did not answer within 5 seconds/i],
    ["unauthorised", /key was not accepted/i],
    ["not-configured", /nothing was sent/i],
    ["http-503", /status 503/],
  ])("explains the reason %s in plain words", async (reason, words) => {
    const { user } = await openConnections({
      "POST /v1/connections/openrouter/test": () => ({ status: "ok", reachable: false, reason }),
    });
    await user.click(within(card("OpenRouter")).getByRole("button", { name: "Test" }));
    const result = await within(card("OpenRouter")).findByRole("status");
    expect(result).toHaveTextContent(words);
    expect(within(result).getByText(reason)).toBeInTheDocument();
  });

  it("never shows a reason outside the fixed set as raw text", async () => {
    const { user } = await openConnections({
      "POST /v1/connections/ollama/test": () => ({ status: "ok", reachable: false, reason: "Traceback: boom at /srv/app.py" }),
    });
    await user.click(within(card("Ollama")).getByRole("button", { name: "Test" }));
    const result = await within(card("Ollama")).findByRole("status");
    expect(result).toHaveTextContent("Not reachable");
    expect(document.body.textContent).not.toContain("Traceback");
  });

  it("shows a friendly line when the test request itself fails", async () => {
    const { user } = await openConnections({
      "POST /v1/connections/ollama/test": () => json({ status: "error", message: "Unexpected token <" }, 500),
    });
    await user.click(within(card("Ollama")).getByRole("button", { name: "Test" }));
    expect(await within(card("Ollama")).findByRole("alert")).toHaveTextContent(/could not complete/i);
    expect(screen.queryByText(/Unexpected token/)).toBeNull();
  });

  it("warns that the OpenRouter test is a cloud request, and only that one", async () => {
    await openConnections();
    expect(within(card("OpenRouter")).getByText(/sends one request to openrouter\.ai/i)).toBeInTheDocument();
    expect(within(card("Ollama")).queryByText(/openrouter\.ai/i)).toBeNull();
  });

  it("disables Test while a test runs", async () => {
    let release: (value: unknown) => void = () => undefined;
    const held = new Promise((resolve) => {
      release = resolve;
    });
    const { user } = await openConnections({ "POST /v1/connections/ollama/test": () => held });
    const button = within(card("Ollama")).getByRole("button", { name: "Test" });
    await user.click(button);
    expect(await within(card("Ollama")).findByRole("button", { name: "Testing" })).toBeDisabled();
    release({ status: "ok", reachable: true, reason: null });
    expect(await within(card("Ollama")).findByText("Reachable")).toBeInTheDocument();
  });

  it("shows a friendly line with Retry when the connections cannot load", async () => {
    const server = settingsServer({ "GET /v1/connections": () => json({ status: "error", message: "boom" }, 500) });
    startApp("#/settings", server);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Connections" }));
    expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
