import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ChatSettings, Connection, ConnectionList } from "../api/settings";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { CHAT_READY, CONNECTIONS, LLAMACPP, OLLAMA, OPENROUTER, settingsServer } from "./test/fixtures";

const UNSET: ChatSettings = { ...CHAT_READY, provider: null, model: null, source: "default", ready: false, reason: "not-configured" };

async function openChat(handlers = {}) {
  const server = settingsServer({ "GET /v1/settings/chat": () => UNSET, ...handlers });
  startApp("#/settings/chat", server);
  await screen.findByRole("region", { name: "Chat" });
  await waitFor(() => expect(screen.queryByText("Loading Chat settings.")).toBeNull());
  return { server, user: userEvent.setup() };
}

function section() {
  return screen.getByRole("region", { name: "Chat" });
}

async function pick(user: ReturnType<typeof userEvent.setup>, name: string, option: string | RegExp) {
  await user.click(within(section()).getByRole("combobox", { name }));
  await user.click(await screen.findByRole("option", { name: option }));
}

function list(...connections: Connection[]): ConnectionList {
  return { ...CONNECTIONS, connections };
}

describe("Chat section", () => {
  it("shows the saved choice with its source and the form", async () => {
    await openChat({ "GET /v1/settings/chat": () => CHAT_READY });
    const chat = section();
    expect(within(chat).getByRole("combobox", { name: "Provider" })).toHaveTextContent("Ollama");
    expect(within(chat).getByRole("textbox", { name: "Model name" })).toHaveValue("qwen3:4b");
    expect(chat).toHaveTextContent("Source: saved");
  });

  it("marks a provider that is not ready with its reason in text and disables it", async () => {
    const noKey = { ...OPENROUTER, fields: [{ ...OPENROUTER.fields[0]!, set: false, last4: null, source: "none" as const }] };
    const { user } = await openChat({ "GET /v1/connections": () => list(OLLAMA, { ...LLAMACPP, installed: false, install_hint: "uv sync --extra llamacpp" }, noKey) });
    await user.click(within(section()).getByRole("combobox", { name: "Provider" }));
    expect(await screen.findByRole("option", { name: /llama\.cpp.*not installed/i })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("option", { name: /OpenRouter.*no key/i })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("option", { name: "Ollama" })).not.toHaveAttribute("aria-disabled", "true");
  });

  it("fills the model field from List models and saves nothing", async () => {
    const { user, server } = await openChat({
      "POST /v1/connections/ollama/models": () => ({ status: "ok", reachable: true, reason: null, models: ["llama3.2", "qwen3:4b"], truncated: false }),
    });
    await pick(user, "Provider", "Ollama");
    await user.click(within(section()).getByRole("button", { name: "List models" }));
    await pick(user, "Models", "qwen3:4b");
    expect(within(section()).getByRole("textbox", { name: "Model name" })).toHaveValue("qwen3:4b");
    expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(0);
  });

  it("says when the list was cut and when the provider could not be reached", async () => {
    const { user } = await openChat({
      "POST /v1/connections/ollama/models": () => ({ status: "ok", reachable: false, reason: "refused", models: [], truncated: false }),
    });
    await pick(user, "Provider", "Ollama");
    await user.click(within(section()).getByRole("button", { name: "List models" }));
    expect(await within(section()).findByText(/connection was refused/i)).toBeInTheDocument();
    expect(within(section()).queryByRole("combobox", { name: "Models" })).toBeNull();
  });

  it("saves a typed model name and shows the choice and source the server returns", async () => {
    let state: ChatSettings = UNSET;
    const { user, server } = await openChat({
      "GET /v1/settings/chat": () => state,
      "PUT /v1/settings/chat": (body: Record<string, unknown>) => {
        state = { ...CHAT_READY, provider: body.provider as string, model: body.model as string };
        return { status: "ok" };
      },
    });
    await pick(user, "Provider", "OpenRouter");
    await user.type(within(section()).getByRole("textbox", { name: "Model name" }), "openai/gpt-4o-mini");
    await user.click(within(section()).getByRole("button", { name: "Save" }));
    expect(await within(section()).findByText("Source: saved")).toBeInTheDocument();
    expect(within(section()).getByRole("textbox", { name: "Model name" })).toHaveValue("openai/gpt-4o-mini");
    expect(server.find("PUT", "/v1/settings/chat")[0]?.body).toEqual({ provider: "openrouter", model: "openai/gpt-4o-mini" });
  });

  it("clears the saved choice", async () => {
    const { user, server } = await openChat({ "GET /v1/settings/chat": () => CHAT_READY, "PUT /v1/settings/chat": () => ({ status: "ok" }) });
    await user.click(within(section()).getByRole("button", { name: "Clear" }));
    expect(server.find("PUT", "/v1/settings/chat")[0]?.body).toBeNull();
  });

  it("shows the Test result as a badge and one sentence, with no provider text", async () => {
    const { user, server } = await openChat({
      "GET /v1/settings/chat": () => CHAT_READY,
      "POST /v1/settings/chat/test": () => ({ status: "ok", ok: false, reason: "timeout", elapsed_ms: 30000, detail: "Traceback: boom" }),
    });
    await user.click(within(section()).getByRole("button", { name: "Test" }));
    const result = await within(section()).findByRole("status");
    expect(within(result).getByText("Not working")).toHaveAttribute("data-slot", "badge");
    expect(within(result).getByText("timeout")).toHaveAttribute("data-slot", "badge");
    expect(result).toHaveTextContent(/did not answer in time/i);
    expect(document.body.textContent).not.toContain("Traceback");
    expect(server.find("POST", "/v1/settings/chat/test")[0]?.body).toEqual({ provider: "ollama", model: "qwen3:4b" });
  });

  it("shows a working result", async () => {
    const { user } = await openChat({
      "GET /v1/settings/chat": () => CHAT_READY,
      "POST /v1/settings/chat/test": () => ({ status: "ok", ok: true, reason: null, elapsed_ms: 420 }),
    });
    await user.click(within(section()).getByRole("button", { name: "Test" }));
    expect(await within(section()).findByText("Working")).toHaveAttribute("data-slot", "badge");
  });

  it("shows a locked choice with the reason and no Save", async () => {
    await openChat({
      "GET /v1/settings/chat": () => ({ ...CHAT_READY, source: "env", locked: true, lock_reason: "Remove ANSWER__PROVIDER from .env to edit it." }),
    });
    const chat = section();
    expect(chat).toHaveTextContent("ANSWER__PROVIDER");
    expect(chat).toHaveTextContent("Ollama");
    expect(chat).toHaveTextContent("qwen3:4b");
    expect(within(chat).queryByRole("button", { name: "Save" })).toBeNull();
    expect(within(chat).queryByRole("textbox")).toBeNull();
  });

  it("states where the choice applies", async () => {
    await openChat();
    expect(section()).toHaveTextContent(/MCP clients of this web server/i);
    expect(section()).toHaveTextContent(/metadata extraction keeps its own model/i);
    expect(section()).toHaveTextContent(/stdio and the CLI read \.env only/i);
  });

  it("states that text leaves this machine only for a cloud provider", async () => {
    const { user } = await openChat();
    await pick(user, "Provider", "Ollama");
    expect(section()).not.toHaveTextContent(/openrouter\.ai/i);
    await pick(user, "Provider", "OpenRouter");
    expect(section()).toHaveTextContent(/questions and retrieved passages are sent to openrouter\.ai/i);
  });

  it("shows a friendly line with Retry when Chat settings cannot load", async () => {
    startApp("#/settings/chat", settingsServer({ "GET /v1/settings/chat": () => json({ status: "error", message: "boom" }, 500) }));
    expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
