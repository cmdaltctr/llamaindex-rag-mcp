import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Connection, ConnectionList } from "../api/settings";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { CONNECTIONS, LLAMACPP, OLLAMA, OPENROUTER, settingsServer, urlField } from "./test/fixtures";

const KEY = "sk-or-secret-1234567890-wxyz"; // gitleaks:allow

function list(...connections: Connection[]): ConnectionList {
  return { ...CONNECTIONS, connections };
}

async function openProviders(handlers = {}) {
  const server = settingsServer(handlers);
  startApp("#/settings/providers", server);
  await screen.findByRole("heading", { level: 3, name: "Ollama" });
  return { server, user: userEvent.setup() };
}

function card(name: string) {
  return screen.getByRole("region", { name });
}

describe("Providers", () => {
  it("lists a card per server entry with Local and Cloud badges in text and the roles", async () => {
    await openProviders();
    expect(screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toEqual(["Ollama", "llama.cpp", "OpenRouter"]);
    expect(within(card("Ollama")).getByText("Local")).toHaveAttribute("data-slot", "badge");
    expect(within(card("OpenRouter")).getByText("Cloud")).toHaveAttribute("data-slot", "badge");
    expect(within(card("Ollama")).getByText("Answers")).toBeInTheDocument();
    expect(within(card("Ollama")).queryByText("Embeddings")).toBeNull();
    expect(within(card("llama.cpp")).getByText("Embeddings")).toBeInTheDocument();
  });

  it("shows read-only values as read-only and the install command when not installed", async () => {
    await openProviders({
      "GET /v1/connections": () => list(OLLAMA, { ...LLAMACPP, installed: false, install_hint: "uv sync --extra llamacpp" }, OPENROUTER),
    });
    const llamacpp = card("llama.cpp");
    expect(within(llamacpp).getByText("Embedding model")).toBeInTheDocument();
    expect(within(llamacpp).getByText("bge-small")).toBeInTheDocument();
    expect(within(llamacpp).getAllByText("(Read-only)").length).toBeGreaterThan(0);
    expect(within(llamacpp).getByText("uv sync --extra llamacpp")).toBeInTheDocument();
    expect(within(card("Ollama")).queryByText(/uv sync/)).toBeNull();
  });

  it("says that saved values apply at once to this web server only, and shows no restart banner", async () => {
    await openProviders();
    const section = screen.getByRole("region", { name: "Providers" });
    expect(section).toHaveTextContent(/apply at once to this web server only/i);
    expect(screen.queryByText(/restart/i)).toBeNull();
  });

  it("shows an environment address as read-only with the variable named", async () => {
    const locked = { ...OLLAMA, fields: [urlField("base_url", "Address", "http://env-host:11434", "env", "Remove OLLAMA_BASE_URL from .env to edit it.")] };
    await openProviders({ "GET /v1/connections": () => list(locked, LLAMACPP, OPENROUTER) });
    const ollama = card("Ollama");
    expect(within(ollama).getByText("Set from environment (read-only here)")).toBeInTheDocument();
    expect(ollama).toHaveTextContent("OLLAMA_BASE_URL");
    expect(within(ollama).getByText("http://env-host:11434")).toBeInTheDocument();
    expect(within(ollama).queryByRole("textbox")).toBeNull();
    expect(within(ollama).queryByRole("button", { name: "Save address" })).toBeNull();
  });

  it("saves an address and shows the address and source the server returns", async () => {
    let value = "http://127.0.0.1:11434";
    let source: "default" | "saved" = "default";
    const { user, server } = await openProviders({
      "GET /v1/connections": () => list({ ...OLLAMA, fields: [urlField("base_url", "Address", value, source)] }, LLAMACPP, OPENROUTER),
      "PUT /v1/connections/ollama": (body: Record<string, unknown>) => {
        value = (body.fields as Record<string, string>).base_url!;
        source = "saved";
        return { status: "ok" };
      },
    });
    const ollama = card("Ollama");
    const input = within(ollama).getByRole("textbox", { name: "Address" });
    expect(within(ollama).getByRole("button", { name: "Save address" })).toBeDisabled();
    await user.clear(input);
    await user.type(input, "http://gpu-box.local:11434");
    await user.click(within(ollama).getByRole("button", { name: "Save address" }));
    expect(await within(ollama).findByText("Source: saved")).toBeInTheDocument();
    expect(within(ollama).getByRole("textbox", { name: "Address" })).toHaveValue("http://gpu-box.local:11434");
    expect(server.find("PUT", "/v1/connections/ollama")[0]?.body).toEqual({ fields: { base_url: "http://gpu-box.local:11434" } });
  });

  it("resets a saved address to the default", async () => {
    const { user, server } = await openProviders({
      "GET /v1/connections": () => list({ ...OLLAMA, fields: [urlField("base_url", "Address", "http://gpu:11434", "saved")] }, LLAMACPP, OPENROUTER),
      "PUT /v1/connections/ollama": () => ({ status: "ok" }),
    });
    await user.click(within(card("Ollama")).getByRole("button", { name: "Reset to default" }));
    expect(server.find("PUT", "/v1/connections/ollama")[0]?.body).toEqual({ fields: { base_url: null } });
  });

  it("states that text leaves this machine for a Cloud card and for a non-loopback address", async () => {
    await openProviders({
      "GET /v1/connections": () => list({ ...OLLAMA, fields: [urlField("base_url", "Address", "http://gpu-box.local:11434", "saved")] }, LLAMACPP, OPENROUTER),
    });
    expect(card("OpenRouter")).toHaveTextContent(/leaves this machine/i);
    expect(card("Ollama")).toHaveTextContent(/leaves this machine/i);
    expect(card("llama.cpp")).not.toHaveTextContent(/leaves this machine/i);
  });

  it("gives the Cloud card its own sentence and a local card the address sentence", async () => {
    await openProviders();
    expect(card("OpenRouter")).toHaveTextContent("Text you send to this provider leaves this machine.");
    expect(card("Ollama")).not.toHaveTextContent("Text you send to this provider leaves this machine.");
  });

  it("shows no leaves-this-machine line for a loopback address", async () => {
    await openProviders();
    expect(card("Ollama")).not.toHaveTextContent(/leaves this machine/i);
  });

  it("shows the key as set with the last four characters and never a full key", async () => {
    await openProviders({
      "GET /v1/connections": () => list(OLLAMA, LLAMACPP, { ...OPENROUTER, fields: [{ ...OPENROUTER.fields[0]!, api_key: KEY } as never] }),
    });
    const openrouter = card("OpenRouter");
    expect(within(openrouter).getByText("Key set")).toBeInTheDocument();
    expect(openrouter).toHaveTextContent("wxyz");
    expect(document.body.textContent).not.toContain(KEY);
    expect(document.body.textContent).not.toContain("secret-1234");
  });

  it("saves a key, empties the input and shows Key set with the last four characters", async () => {
    let saved = false;
    const keyField = OPENROUTER.fields[0]!;
    const { user, server } = await openProviders({
      "GET /v1/connections": () =>
        list(OLLAMA, LLAMACPP, {
          ...OPENROUTER,
          fields: [saved ? keyField : { ...keyField, set: false, last4: null, source: "none", saved_at: null }],
        }),
      "PUT /v1/connections/openrouter/key": () => {
        saved = true;
        return { status: "ok" };
      },
    });
    const openrouter = card("OpenRouter");
    expect(within(openrouter).getByText("No key")).toBeInTheDocument();
    const input = within(openrouter).getByLabelText("API key");
    expect(input).toHaveAttribute("type", "password");
    expect(input).toHaveAttribute("autocomplete", "off");
    await user.type(input, KEY);
    await user.click(within(openrouter).getByRole("button", { name: "Save key" }));
    expect(await within(openrouter).findByText("Key set")).toBeInTheDocument();
    expect(openrouter).toHaveTextContent("wxyz");
    expect(within(openrouter).getByLabelText("API key")).toHaveValue("");
    expect(server.find("PUT", "/v1/connections/openrouter/key")[0]?.body).toEqual({ api_key: KEY });
    expect(document.body.textContent).not.toContain(KEY);
  });

  it("removes a key kept in the keychain", async () => {
    const { user, server } = await openProviders({ "DELETE /v1/connections/openrouter/key": () => ({ status: "ok" }) });
    await user.click(within(card("OpenRouter")).getByRole("button", { name: "Remove key" }));
    expect(server.find("DELETE", "/v1/connections/openrouter/key")).toHaveLength(1);
  });

  it("shows an environment key as read-only with no key input", async () => {
    const envKey = { ...OPENROUTER.fields[0]!, source: "env" as const, locked: true, lock_reason: "Remove OPENROUTER_API_KEY from .env to edit it." };
    await openProviders({ "GET /v1/connections": () => list(OLLAMA, LLAMACPP, { ...OPENROUTER, fields: [envKey] }) });
    const openrouter = card("OpenRouter");
    expect(within(openrouter).getByText("Set from environment (read-only here)")).toBeInTheDocument();
    expect(openrouter).toHaveTextContent("OPENROUTER_API_KEY");
    expect(within(openrouter).queryByLabelText("API key")).toBeNull();
    expect(within(openrouter).queryByRole("button", { name: "Remove key" })).toBeNull();
  });

  it("replaces the key input with one line when no keychain is available", async () => {
    const noKey = { ...OPENROUTER.fields[0]!, set: false, last4: null, source: "none" as const, lock_reason: "No system keychain is available. Set OPENROUTER_API_KEY in the environment or .env." };
    await openProviders({ "GET /v1/connections": () => ({ ...list(OLLAMA, LLAMACPP, { ...OPENROUTER, fields: [noKey] }), keychain: "unavailable" }) });
    const openrouter = card("OpenRouter");
    expect(openrouter).toHaveTextContent(/no system keychain/i);
    expect(openrouter.textContent?.match(/no system keychain/gi)).toHaveLength(1);
    expect(openrouter).toHaveTextContent("OPENROUTER_API_KEY");
    expect(within(openrouter).queryByLabelText("API key")).toBeNull();
    expect(within(openrouter).queryByRole("button", { name: "Save key" })).toBeNull();
  });

  it.each([
    ["keychain-missing", /removed from the keychain/i],
    ["keychain-unreadable", /could not be read/i],
  ])("explains the key state %s", async (state, words) => {
    const field = { ...OPENROUTER.fields[0]!, set: false, last4: null, source: "none" as const, state };
    await openProviders({ "GET /v1/connections": () => list(OLLAMA, LLAMACPP, { ...OPENROUTER, fields: [field] }) });
    expect(card("OpenRouter")).toHaveTextContent(words);
  });

  it("sends no provider request until Test is pressed", async () => {
    const { server } = await openProviders();
    expect(server.calls.filter((call) => call.method !== "GET")).toHaveLength(0);
  });

  it("tests a typed address without saving it", async () => {
    const { user, server } = await openProviders({
      "POST /v1/connections/ollama/test": () => ({ status: "ok", reachable: false, reason: "refused" }),
    });
    const ollama = card("Ollama");
    const input = within(ollama).getByRole("textbox", { name: "Address" });
    await user.clear(input);
    await user.type(input, "http://gpu:11434");
    await user.click(within(ollama).getByRole("button", { name: "Test" }));
    const result = await within(ollama).findByRole("status");
    expect(within(result).getByText("Not reachable")).toBeInTheDocument();
    expect(within(result).getByText("refused")).toHaveAttribute("data-slot", "badge");
    expect(result).toHaveTextContent(/connection was refused/i);
    expect(server.find("POST", "/v1/connections/ollama/test")[0]?.body).toEqual({ fields: { base_url: "http://gpu:11434" } });
    expect(server.find("PUT", "/v1/connections")).toHaveLength(0);
  });

  it("tests a typed key and sends it only in the test body", async () => {
    const { user, server } = await openProviders({
      "POST /v1/connections/openrouter/test": () => ({ status: "ok", reachable: false, reason: "unauthorised" }),
    });
    const openrouter = card("OpenRouter");
    await user.type(within(openrouter).getByLabelText("API key"), KEY);
    await user.click(within(openrouter).getByRole("button", { name: "Test" }));
    expect(await within(openrouter).findByText("unauthorised")).toBeInTheDocument();
    expect(server.find("POST", "/v1/connections/openrouter/test")[0]?.body).toEqual({ fields: { api_key: KEY } });
    expect(document.body.textContent).not.toContain(KEY);
  });

  it("tests the saved values with an empty body when nothing is typed", async () => {
    const { user, server } = await openProviders({ "POST /v1/connections/ollama/test": () => ({ status: "ok", reachable: true, reason: null }) });
    await user.click(within(card("Ollama")).getByRole("button", { name: "Test" }));
    expect(await within(card("Ollama")).findByText("Reachable")).toHaveAttribute("data-slot", "badge");
    expect(server.find("POST", "/v1/connections/ollama/test")[0]?.body).toEqual({ fields: {} });
  });

  it("never shows a reason outside the fixed set as raw text", async () => {
    const { user } = await openProviders({
      "POST /v1/connections/ollama/test": () => ({ status: "ok", reachable: false, reason: "Traceback: boom at /srv/app.py" }),
    });
    await user.click(within(card("Ollama")).getByRole("button", { name: "Test" }));
    expect(await within(card("Ollama")).findByText("Not reachable")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("Traceback");
  });

  it("shows one friendly line when a save fails and no server text", async () => {
    const { user } = await openProviders({
      "PUT /v1/connections/ollama": () => json({ status: "error", message: "locked by OLLAMA_BASE_URL at /srv/x" }, 409),
    });
    const ollama = card("Ollama");
    await user.type(within(ollama).getByRole("textbox", { name: "Address" }), "x");
    await user.click(within(ollama).getByRole("button", { name: "Save address" }));
    expect(await within(ollama).findByRole("alert")).toHaveTextContent(/could not complete/i);
    expect(screen.queryByText(/\/srv\/x/)).toBeNull();
  });

  it("shows a friendly line with Retry when the providers cannot load", async () => {
    startApp("#/settings/providers", settingsServer({ "GET /v1/connections": () => json({ status: "error", message: "boom" }, 500) }));
    expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
