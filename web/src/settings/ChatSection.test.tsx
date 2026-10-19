import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ChatSettings, Connection, ConnectionList, ProviderField } from "../api/settings";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { CHAT_READY, CONNECTIONS, LLAMACPP, OLLAMA, OPENROUTER, settingsServer, urlField } from "./test/fixtures";

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

async function edit(user: ReturnType<typeof userEvent.setup>) {
  await user.click(within(section()).getByRole("button", { name: "Edit Chat model" }));
}

async function pick(user: ReturnType<typeof userEvent.setup>, name: string, option: string | RegExp) {
  await user.click(within(section()).getByRole("combobox", { name }));
  await user.click(await screen.findByRole("option", { name: option }));
}

function list(...connections: Connection[]): ConnectionList {
  return { ...CONNECTIONS, connections };
}

describe("Chat section", () => {
  it("shows the provider and the model as rows with their source, and no form until Edit", async () => {
    const { user } = await openChat({ "GET /v1/settings/chat": () => CHAT_READY });
    const chat = section();
    expect(within(chat).getByText("Ollama")).toBeInTheDocument();
    expect(within(chat).getByText("qwen3:4b")).toBeInTheDocument();
    expect(within(chat).getAllByText("from omrg.jsonc")).toHaveLength(2);
    expect(within(chat).queryByRole("combobox")).toBeNull();
    await edit(user);
    expect(within(chat).getByRole("combobox", { name: "Provider" })).toHaveTextContent("Ollama");
    expect(within(chat).getByRole("textbox", { name: "Model name" })).toHaveValue("qwen3:4b");
  });

  it("shows the default words and no Clear when nothing is saved", async () => {
    const { user } = await openChat();
    expect(section()).toHaveTextContent("default");
    await edit(user);
    expect(within(section()).queryByRole("button", { name: "Clear" })).toBeNull();
  });

  it("closes the form on Cancel and saves nothing", async () => {
    const { user, server } = await openChat({ "GET /v1/settings/chat": () => CHAT_READY });
    await edit(user);
    await user.type(within(section()).getByRole("textbox", { name: "Model name" }), "x");
    await user.click(within(section()).getByRole("button", { name: "Cancel" }));
    expect(within(section()).queryByRole("textbox")).toBeNull();
    expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(0);
  });

  it("marks a provider that is not ready with its reason in text and disables it", async () => {
    const noKey = { ...OPENROUTER, fields: [{ ...OPENROUTER.fields[0]!, set: false, last4: null, source: "none" as const }] };
    const { user } = await openChat({ "GET /v1/connections": () => list(OLLAMA, { ...LLAMACPP, installed: false, install_hint: "uv sync --extra llamacpp" }, noKey) });
    await edit(user);
    await user.click(within(section()).getByRole("combobox", { name: "Provider" }));
    expect(await screen.findByRole("option", { name: /llama\.cpp.*not installed/i })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("option", { name: /OpenRouter.*no key/i })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("option", { name: "Ollama" })).not.toHaveAttribute("aria-disabled", "true");
  });

  it("lets Chat use a provider whose optional key is empty and shows the install hint of a missing package", async () => {
    // `required: false` is the server flag for a key that a provider can run without (LM Studio, vLLM).
    const openAiCompatible: Connection = {
      provider: "openai_compatible",
      display_name: "OpenAI-compatible",
      locality: "cloud",
      installed: true,
      install_hint: null,
      fields: [
        urlField("base_url", "Address", "http://127.0.0.1:1234/v1"),
        { ...OPENROUTER.fields[0]!, set: false, last4: null, source: "none" as const, required: false } as ProviderField,
      ],
      read_only: [],
      roles: ["answers"],
    };
    const anthropic: Connection = {
      provider: "anthropic",
      display_name: "Anthropic",
      locality: "cloud",
      installed: false,
      install_hint: "uv sync --extra anthropic",
      fields: [{ ...OPENROUTER.fields[0]!, set: false, last4: null, source: "none" as const }],
      read_only: [],
      roles: ["answers"],
    };
    const { user } = await openChat({ "GET /v1/connections": () => list(OLLAMA, openAiCompatible, anthropic) });
    await edit(user);
    await user.click(within(section()).getByRole("combobox", { name: "Provider" }));
    const optionalKey = await screen.findByRole("option", { name: /OpenAI-compatible/ });
    expect(optionalKey).not.toHaveAttribute("aria-disabled", "true");
    expect(optionalKey).not.toHaveTextContent(/no key/i);
    expect(screen.getByRole("option", { name: /Anthropic.*not installed/i })).toHaveAttribute("aria-disabled", "true");
  });

  it("fills the model field from List models and saves nothing", async () => {
    const { user, server } = await openChat({
      "POST /v1/connections/ollama/models": () => ({ status: "ok", reachable: true, reason: null, models: ["llama3.2", "qwen3:4b"], truncated: false }),
    });
    await edit(user);
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
    await edit(user);
    await pick(user, "Provider", "Ollama");
    await user.click(within(section()).getByRole("button", { name: "List models" }));
    expect(await within(section()).findByText(/connection was refused/i)).toBeInTheDocument();
    expect(within(section()).queryByRole("combobox", { name: "Models" })).toBeNull();
  });

  it("tells the user when the model list was cut", async () => {
    const { user } = await openChat({
      "POST /v1/connections/ollama/models": () => ({ status: "ok", reachable: true, reason: null, models: ["llama3.2"], truncated: true }),
    });
    await edit(user);
    await pick(user, "Provider", "Ollama");
    await user.click(within(section()).getByRole("button", { name: "List models" }));
    expect(await within(section()).findByText(/the list was cut/i)).toBeInTheDocument();
  });

  it("disables Save and sends nothing while the model name is empty", async () => {
    const { user, server } = await openChat();
    await edit(user);
    await pick(user, "Provider", "Ollama");
    const save = within(section()).getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    await user.type(within(section()).getByRole("textbox", { name: "Model name" }), "{Enter}");
    expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(0);
  });

  it("saves a typed model name, closes the form and shows the choice and source the server returns", async () => {
    let state: ChatSettings = UNSET;
    const { user, server } = await openChat({
      "GET /v1/settings/chat": () => state,
      "PUT /v1/settings/chat": (body: Record<string, unknown>) => {
        state = { ...CHAT_READY, provider: body.provider as string, model: body.model as string };
        return { status: "ok", revision: "r2" };
      },
    });
    await edit(user);
    await pick(user, "Provider", "OpenRouter");
    await user.type(within(section()).getByRole("textbox", { name: "Model name" }), "openai/gpt-4o-mini");
    await user.click(within(section()).getByRole("button", { name: "Save" }));
    expect(await within(section()).findAllByText("from omrg.jsonc")).toHaveLength(2);
    expect(within(section()).getByText("openai/gpt-4o-mini")).toBeInTheDocument();
    expect(within(section()).queryByRole("textbox")).toBeNull();
    expect(server.find("PUT", "/v1/settings/chat")[0]?.body).toEqual({ provider: "openrouter", model: "openai/gpt-4o-mini", revision: "r1" });
  });

  it("clears the saved choice with only the revision in the body", async () => {
    const { user, server } = await openChat({ "GET /v1/settings/chat": () => CHAT_READY, "PUT /v1/settings/chat": () => ({ status: "ok", revision: "r2" }) });
    await edit(user);
    await user.click(within(section()).getByRole("button", { name: "Clear" }));
    expect(server.find("PUT", "/v1/settings/chat")[0]?.body).toEqual({ revision: "r1" });
  });

  it("shows the Test result as a badge and one sentence, with no provider text", async () => {
    const { user, server } = await openChat({
      "GET /v1/settings/chat": () => CHAT_READY,
      "POST /v1/settings/chat/test": () => ({ status: "ok", ok: false, reason: "timeout", elapsed_ms: 30000, detail: "Traceback: boom" }),
    });
    await edit(user);
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
    await edit(user);
    await user.click(within(section()).getByRole("button", { name: "Test" }));
    expect(await within(section()).findByText("Working")).toHaveAttribute("data-slot", "badge");
  });

  it.each([
    ["env", "Set in the environment. Change it there."],
    ["dotenv", "Set in .env. Change it there."],
  ] as const)("shows a choice set by %s as locked with the variable named and offers no Edit", async (source, words) => {
    await openChat({
      "GET /v1/settings/chat": () => ({ ...CHAT_READY, source, locked: true, lock_reason: "Set by ANSWER__PROVIDER and ANSWER__MODEL in the environment or .env. Remove it to edit here." }),
    });
    const chat = section();
    expect(chat).toHaveTextContent("ANSWER__PROVIDER");
    expect(chat).toHaveTextContent(words);
    expect(chat).toHaveTextContent("Ollama");
    expect(chat).toHaveTextContent("qwen3:4b");
    expect(within(chat).queryByRole("button", { name: "Edit Chat model" })).toBeNull();
    expect(within(chat).queryByRole("textbox")).toBeNull();
  });

  it("shows the rule message when a save is refused with 400", async () => {
    const message = "The model name is not valid.";
    const { user } = await openChat({ "GET /v1/settings/chat": () => CHAT_READY, "PUT /v1/settings/chat": () => json({ status: "error", message }, 400) });
    await edit(user);
    await user.type(within(section()).getByRole("textbox", { name: "Model name" }), "x");
    await user.click(within(section()).getByRole("button", { name: "Save" }));
    expect(await within(section()).findByRole("alert")).toHaveTextContent(message);
  });

  it("shows the conflict with Reload when omrg.jsonc changed on disk, and reads the choice again on Reload", async () => {
    const message = "omrg.jsonc changed on disk. Reload to see the new values.";
    const { user, server } = await openChat({ "GET /v1/settings/chat": () => CHAT_READY, "PUT /v1/settings/chat": () => json({ status: "error", message }, 409) });
    await edit(user);
    await user.type(within(section()).getByRole("textbox", { name: "Model name" }), "x");
    await user.click(within(section()).getByRole("button", { name: "Save" }));
    expect(await within(section()).findByRole("alert")).toHaveTextContent(message);
    const reads = server.find("GET", "/v1/settings/chat").length;
    await user.click(within(section()).getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(server.find("GET", "/v1/settings/chat").length).toBe(reads + 1));
  });

  it("states where the choice applies", async () => {
    await openChat();
    expect(section()).toHaveTextContent(/MCP clients of this web server/i);
    expect(section()).toHaveTextContent(/metadata extraction keeps its own model/i);
    expect(section()).toHaveTextContent(/stdio and the CLI read the same omrg\.jsonc at their next launch/i);
  });

  it("states that text leaves this machine only for a cloud provider", async () => {
    const { user } = await openChat();
    await edit(user);
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
