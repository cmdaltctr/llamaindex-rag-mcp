import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Connection, ConnectionList, ProviderField } from "../api/settings";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { CONFIG_DIR, CONNECTIONS, LLAMACPP, OLLAMA, OPENROUTER, settingsServer, urlField } from "./test/fixtures";

const KEY = "sk-or-secret-1234567890-wxyz"; // gitleaks:allow

function list(...connections: Connection[]): ConnectionList {
  return { ...CONNECTIONS, connections };
}

function openrouter(change: Partial<ProviderField>): Connection {
  return { ...OPENROUTER, fields: [{ ...OPENROUTER.fields[0]!, ...change }] };
}

const NO_KEY: Partial<ProviderField> = { set: false, last4: null, source: "none" };

/**
 * Fakes layout sizes: the masonry area is *width* pixels wide and each card has
 * the height given for its title. Returns a function that sets new heights and
 * one that restores the real method.
 */
function fakeSizes(width: number, heights: Record<string, number> = {}) {
  const original = HTMLElement.prototype.getBoundingClientRect;
  let current = heights;
  HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
    let w = 0;
    let h = 0;
    if (this.dataset.testid === "masonry") w = width;
    if (this.dataset.masonryItem !== undefined) h = current[this.querySelector("h3")?.textContent ?? ""] ?? 0;
    return { width: w, height: h, top: 0, left: 0, right: w, bottom: h, x: 0, y: 0, toJSON: () => ({}) } as DOMRect;
  };
  return {
    setHeights: (next: Record<string, number>) => {
      current = next;
    },
    restore: () => {
      HTMLElement.prototype.getBoundingClientRect = original;
    },
  };
}

/** Replaces the no-op ResizeObserver stub with one whose callbacks the test can fire. */
function fakeResizeObserver() {
  const original = globalThis.ResizeObserver;
  const callbacks = new Set<() => void>();
  const observed = new Set<Element>();
  globalThis.ResizeObserver = class {
    private readonly callback: () => void;
    constructor(callback: () => void) {
      this.callback = callback;
      callbacks.add(callback);
    }
    observe(target: Element) {
      observed.add(target);
    }
    unobserve(target: Element) {
      observed.delete(target);
    }
    disconnect() {
      callbacks.delete(this.callback);
      observed.clear();
    }
  } as unknown as typeof ResizeObserver;
  return {
    observed,
    fire: () => callbacks.forEach((callback) => callback()),
    restore: () => {
      globalThis.ResizeObserver = original;
    },
  };
}

const FIVE = () =>
  list(
    OLLAMA,
    LLAMACPP,
    OPENROUTER,
    { ...OPENROUTER, provider: "openai_compatible", display_name: "OpenAI-compatible" },
    { ...OPENROUTER, provider: "anthropic", display_name: "Anthropic" },
  );

const TALL_LLAMA = { Ollama: 400, "llama.cpp": 1000, OpenRouter: 380, "OpenAI-compatible": 450, Anthropic: 370 };

function names(column: HTMLElement) {
  return within(column).getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent);
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

  it("keeps a card with an extra panel in one column, with the panel under the fields", async () => {
    await openProviders();
    const llamacpp = card("llama.cpp");
    expect(llamacpp.className).not.toMatch(/col-span/);
    const panel = await within(llamacpp).findByRole("heading", { level: 4, name: "Local server" });
    const extra = panel.closest("[data-slot='provider-extra']") as HTMLElement;
    expect(extra).not.toBeNull();
    expect(extra.className).not.toMatch(/border-l/);
    expect(extra.parentElement?.className ?? "").not.toMatch(/grid-cols-2/);
    expect(within(extra).queryByRole("button", { name: "Test" })).toBeNull();
  });

  it("fits as many 300 px columns as the area allows, up to three", async () => {
    const sizes = fakeSizes(700);
    try {
      await openProviders();
      await waitFor(() => expect(screen.getAllByTestId("masonry-column")).toHaveLength(2));
      const columns = screen.getAllByTestId("masonry-column");
      expect(names(columns[0]!)).toEqual(["Ollama", "OpenRouter"]);
      expect(names(columns[1]!)).toEqual(["llama.cpp"]);
    } finally {
      sizes.restore();
    }
  });

  it("puts each card in the shortest column, so a short card does not sit under a tall one", async () => {
    const sizes = fakeSizes(1000, TALL_LLAMA);
    try {
      await openProviders({ "GET /v1/connections": FIVE });
      // Dealt in turn, Anthropic would sit under the 1000 px llama.cpp card.
      await waitFor(() => expect(names(screen.getAllByTestId("masonry-column")[0]!)).toEqual(["Ollama", "Anthropic"]));
      const columns = screen.getAllByTestId("masonry-column");
      expect(columns).toHaveLength(3);
      expect(names(columns[1]!)).toEqual(["llama.cpp"]);
      expect(names(columns[2]!)).toEqual(["OpenRouter", "OpenAI-compatible"]);
    } finally {
      sizes.restore();
    }
  });

  it("does not move a card while focus is inside the cards, and places them again when focus leaves", async () => {
    const sizes = fakeSizes(1000, TALL_LLAMA);
    const resizes = fakeResizeObserver();
    try {
      const { user } = await openProviders({ "GET /v1/connections": FIVE });
      await waitFor(() => expect(names(screen.getAllByTestId("masonry-column")[0]!)).toEqual(["Ollama", "Anthropic"]));
      // Ollama grows while the user edits it; Anthropic would now fit better under OpenRouter.
      await user.click(within(card("Ollama")).getAllByRole("button", { name: /edit/i })[0]!);
      const field = within(card("Ollama")).getAllByRole("textbox")[0]!;
      act(() => field.focus());
      sizes.setHeights({ ...TALL_LLAMA, Ollama: 900 });
      await act(async () => {
        resizes.fire();
        await new Promise((resolve) => requestAnimationFrame(resolve));
      });
      expect(names(screen.getAllByTestId("masonry-column")[0]!)).toEqual(["Ollama", "Anthropic"]);
      act(() => field.blur());
      await waitFor(() => expect(names(screen.getAllByTestId("masonry-column")[0]!)).toEqual(["Ollama"]));
    } finally {
      resizes.restore();
      sizes.restore();
    }
  });

  it("keeps watching a card's size after it moves to another column", async () => {
    const sizes = fakeSizes(1000, TALL_LLAMA);
    const resizes = fakeResizeObserver();
    try {
      await openProviders({ "GET /v1/connections": FIVE });
      await waitFor(() => expect(names(screen.getAllByTestId("masonry-column")[0]!)).toEqual(["Ollama", "Anthropic"]));
      // Ollama grows (a panel finished loading) with three columns still in place: Anthropic
      // moves to the OpenRouter column, so React gives it a new element.
      sizes.setHeights({ ...TALL_LLAMA, Ollama: 900 });
      await act(async () => {
        resizes.fire();
        await new Promise((resolve) => requestAnimationFrame(resolve));
      });
      await waitFor(() => expect(names(screen.getAllByTestId("masonry-column")[0]!)).toEqual(["Ollama"]));
      const items = Array.from(document.querySelectorAll("[data-masonry-item]"));
      expect(items).toHaveLength(5);
      for (const item of items) expect(resizes.observed.has(item)).toBe(true);
    } finally {
      resizes.restore();
      sizes.restore();
    }
  });

  it("stacks every card in one column on a phone", async () => {
    const sizes = fakeSizes(358);
    try {
      await openProviders();
      expect(screen.getAllByTestId("masonry-column")).toHaveLength(1);
    } finally {
      sizes.restore();
    }
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

  it("names the omrs.jsonc path, says saves are written there, and shows no restart banner", async () => {
    await openProviders();
    const section = screen.getByRole("region", { name: "Providers" });
    expect(section).toHaveTextContent("~/.config/omrs/omrs.jsonc");
    expect(section).toHaveTextContent(/saves are written to .*omrs\.jsonc/i);
    expect(section).toHaveTextContent(/apply at once to this web server/i);
    expect(screen.queryByText(/restart to apply/i)).toBeNull();
  });

  it("shows an address with the default word and an Edit button, and no input until Edit", async () => {
    await openProviders();
    const ollama = card("Ollama");
    expect(within(ollama).getByText("http://127.0.0.1:11434")).toBeInTheDocument();
    expect(within(ollama).getByText("default")).toBeInTheDocument();
    expect(within(ollama).queryByRole("textbox")).toBeNull();
    expect(within(ollama).getByRole("button", { name: "Edit Address" })).toBeInTheDocument();
  });

  it("shows an environment address as read-only with the variable named", async () => {
    const locked = { ...OLLAMA, fields: [urlField("base_url", "Address", "http://env-host:11434", "env", "Remove OLLAMA_BASE_URL from the environment or .env to edit it here.")] };
    await openProviders({ "GET /v1/connections": () => list(locked, LLAMACPP, OPENROUTER) });
    const ollama = card("Ollama");
    expect(within(ollama).getByText("Set in the environment. Change it there.")).toBeInTheDocument();
    expect(ollama).toHaveTextContent("OLLAMA_BASE_URL");
    expect(within(ollama).getByText("http://env-host:11434")).toBeInTheDocument();
    expect(within(ollama).queryByRole("textbox")).toBeNull();
    expect(within(ollama).queryByRole("button", { name: /^Edit/ })).toBeNull();
  });

  it("shows a .env address as read-only with the variable and the .env path", async () => {
    const locked = { ...OLLAMA, fields: [urlField("base_url", "Address", "http://env-host:11434", "dotenv", "Remove OLLAMA_BASE_URL from the environment or .env to edit it here.")] };
    await openProviders({ "GET /v1/connections": () => list(locked, LLAMACPP, OPENROUTER) });
    const ollama = card("Ollama");
    expect(ollama).toHaveTextContent("Set in .env. Change it there.");
    expect(ollama).toHaveTextContent("OLLAMA_BASE_URL");
    expect(ollama).toHaveTextContent(`${CONFIG_DIR}/.env`);
    expect(within(ollama).queryByRole("button", { name: /^Edit/ })).toBeNull();
  });

  it("shows an address from the config file with its words and keeps it editable", async () => {
    await openProviders({
      "GET /v1/connections": () => list({ ...OLLAMA, fields: [urlField("base_url", "Address", "http://cfg-host:11434", "config-file")] }, LLAMACPP, OPENROUTER),
    });
    const ollama = card("Ollama");
    expect(within(ollama).getByText("http://cfg-host:11434")).toBeInTheDocument();
    expect(within(ollama).getByText("from omrs.jsonc")).toBeInTheDocument();
    expect(within(ollama).getByRole("button", { name: "Edit Address" })).toBeInTheDocument();
  });

  it("opens the input filled with the address, saves it and shows the address and source the server returns", async () => {
    let value = "http://127.0.0.1:11434";
    let source: "default" | "config-file" = "default";
    const { user, server } = await openProviders({
      "GET /v1/connections": () => list({ ...OLLAMA, fields: [urlField("base_url", "Address", value, source)] }, LLAMACPP, OPENROUTER),
      "PUT /v1/connections/ollama": (body: Record<string, unknown>) => {
        value = (body.fields as Record<string, string>).base_url!;
        source = "config-file";
        return { status: "ok", revision: "r2" };
      },
    });
    const ollama = card("Ollama");
    await user.click(within(ollama).getByRole("button", { name: "Edit Address" }));
    const input = within(ollama).getByRole("textbox", { name: "Address" });
    expect(input).toHaveValue("http://127.0.0.1:11434");
    expect(within(ollama).getByRole("button", { name: "Save" })).toBeDisabled();
    await user.clear(input);
    await user.type(input, "http://gpu-box.local:11434");
    await user.click(within(ollama).getByRole("button", { name: "Save" }));
    expect(await within(ollama).findByText("from omrs.jsonc")).toBeInTheDocument();
    expect(within(ollama).getByText("http://gpu-box.local:11434")).toBeInTheDocument();
    expect(within(ollama).queryByRole("textbox")).toBeNull();
    expect(server.find("PUT", "/v1/connections/ollama")[0]?.body).toEqual({ fields: { base_url: "http://gpu-box.local:11434" }, revision: "r1" });
  });

  it("returns a file address to the default with null", async () => {
    const { user, server } = await openProviders({
      "GET /v1/connections": () => list({ ...OLLAMA, fields: [urlField("base_url", "Address", "http://gpu:11434", "config-file")] }, LLAMACPP, OPENROUTER),
      "PUT /v1/connections/ollama": () => ({ status: "ok", revision: "r2" }),
    });
    await user.click(within(card("Ollama")).getByRole("button", { name: "Edit Address" }));
    await user.click(within(card("Ollama")).getByRole("button", { name: "Use default" }));
    expect(server.find("PUT", "/v1/connections/ollama")[0]?.body).toEqual({ fields: { base_url: null }, revision: "r1" });
  });

  it("states that text leaves this machine for a Cloud card and for a non-loopback address", async () => {
    await openProviders({
      "GET /v1/connections": () => list({ ...OLLAMA, fields: [urlField("base_url", "Address", "http://gpu-box.local:11434", "config-file")] }, LLAMACPP, OPENROUTER),
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

  it("shows a keychain key as a summary row with Replace and Remove, and never a full key", async () => {
    await openProviders({
      "GET /v1/connections": () => list(OLLAMA, LLAMACPP, { ...OPENROUTER, fields: [{ ...OPENROUTER.fields[0]!, api_key: KEY } as never] }),
    });
    const openrouter = card("OpenRouter");
    expect(within(openrouter).getByText("Key set · ending wxyz · in system keychain")).toBeInTheDocument();
    expect(within(openrouter).getByRole("button", { name: "Replace API key" })).toBeInTheDocument();
    expect(within(openrouter).getByRole("button", { name: "Remove API key" })).toBeInTheDocument();
    expect(within(openrouter).queryByLabelText("API key")).toBeNull();
    expect(document.body.textContent).not.toContain(KEY);
    expect(document.body.textContent).not.toContain("secret-1234");
  });

  it("shows a key from .env with its words and no button", async () => {
    await openProviders({ "GET /v1/connections": () => list(OLLAMA, LLAMACPP, openrouter({ source: "dotenv", locked: true, lock_reason: "Remove OPENROUTER_API_KEY from the environment or .env to edit it here." })) });
    const card_ = card("OpenRouter");
    expect(within(card_).getByText("Key set · ending wxyz · Set in .env. Change it there.")).toBeInTheDocument();
    expect(within(card_).queryByRole("button", { name: /Replace|Remove/ })).toBeNull();
    expect(within(card_).queryByLabelText("API key")).toBeNull();
  });

  it("shows a key from the environment with its words and no button", async () => {
    await openProviders({ "GET /v1/connections": () => list(OLLAMA, LLAMACPP, openrouter({ source: "env", locked: true, lock_reason: "Remove OPENROUTER_API_KEY from the environment or .env to edit it here." })) });
    const card_ = card("OpenRouter");
    expect(within(card_).getByText("Key set · ending wxyz · Set in the environment. Change it there.")).toBeInTheDocument();
    expect(within(card_).queryByRole("button", { name: /Replace|Remove/ })).toBeNull();
  });

  it("shows a key from a key file with the file, offers Replace and no Remove", async () => {
    await openProviders({ "GET /v1/connections": () => list(OLLAMA, LLAMACPP, openrouter({ source: "key-file" })) });
    const card_ = card("OpenRouter");
    expect(within(card_).getByText("Key set · ending wxyz · from key file secrets/openrouter.key")).toBeInTheDocument();
    expect(within(card_).getByRole("button", { name: "Replace API key" })).toBeInTheDocument();
    expect(within(card_).queryByRole("button", { name: /^Remove/ })).toBeNull();
  });

  it("replaces a key: the input closes, the summary shows the new ending and the key is never shown again", async () => {
    let saved = false;
    const { user, server } = await openProviders({
      "GET /v1/connections": () => list(OLLAMA, LLAMACPP, saved ? openrouter({ last4: "9999" }) : openrouter({ last4: "wxyz" })),
      "PUT /v1/connections/openrouter/key": () => {
        saved = true;
        return { status: "ok", revision: "r2" };
      },
    });
    const card_ = card("OpenRouter");
    await user.click(within(card_).getByRole("button", { name: "Replace API key" }));
    const input = within(card_).getByLabelText("API key");
    expect(input).toHaveValue("");
    expect(input).toHaveAttribute("type", "password");
    expect(input).toHaveAttribute("autocomplete", "off");
    await user.type(input, KEY);
    await user.click(within(card_).getByRole("button", { name: "Save key" }));
    expect(await within(card_).findByText("Key set · ending 9999 · in system keychain")).toBeInTheDocument();
    expect(within(card_).queryByLabelText("API key")).toBeNull();
    expect(server.find("PUT", "/v1/connections/openrouter/key")[0]?.body).toEqual({ api_key: KEY, revision: "r1" });
    expect(document.body.textContent).not.toContain(KEY);
  });

  it("removes a key kept in the keychain", async () => {
    const { user, server } = await openProviders({ "DELETE /v1/connections/openrouter/key": () => ({ status: "ok", revision: "r2" }) });
    await user.click(within(card("OpenRouter")).getByRole("button", { name: "Remove API key" }));
    expect(server.find("DELETE", "/v1/connections/openrouter/key")).toHaveLength(1);
    expect(server.find("DELETE", "/v1/connections/openrouter/key")[0]?.body).toEqual({ revision: "r1" });
  });

  it("shows a key input with the placeholder and the key file hint when no key is set", async () => {
    await openProviders({ "GET /v1/connections": () => list(OLLAMA, LLAMACPP, openrouter(NO_KEY)) });
    const card_ = card("OpenRouter");
    expect(within(card_).getByLabelText("API key")).toHaveAttribute("placeholder", "Paste key (saved to the system keychain)");
    expect(within(card_).getByText("Or put it in secrets/openrouter.key")).toBeInTheDocument();
    expect(within(card_).queryByText(/Key set/)).toBeNull();
  });

  it("shows an optional key as optional with no error", async () => {
    const optional: Connection = { ...OPENROUTER, provider: "openai_compatible", display_name: "OpenAI-compatible", fields: [{ ...OPENROUTER.fields[0]!, ...NO_KEY, required: false }] };
    await openProviders({ "GET /v1/connections": () => list(OLLAMA, LLAMACPP, optional) });
    const card_ = card("OpenAI-compatible");
    expect(within(card_).getByText("Optional")).toBeInTheDocument();
    expect(within(card_).queryByRole("alert")).toBeNull();
  });

  it("replaces the key input with one line when no keychain is available", async () => {
    await openProviders({ "GET /v1/connections": () => ({ ...list(OLLAMA, LLAMACPP, openrouter(NO_KEY)), keychain: "unavailable" }) });
    const card_ = card("OpenRouter");
    expect(card_).toHaveTextContent(/no system keychain/i);
    expect(card_.textContent?.match(/no system keychain/gi)).toHaveLength(1);
    expect(card_).toHaveTextContent("secrets/openrouter.key");
    expect(card_).toHaveTextContent("OPENROUTER_API_KEY");
    expect(within(card_).queryByLabelText("API key")).toBeNull();
    expect(within(card_).queryByRole("button", { name: "Save key" })).toBeNull();
  });

  it.each([
    ["keychain-missing", /removed from the keychain/i],
    ["keychain-unreadable", /could not be read/i],
  ])("explains the key state %s", async (state, words) => {
    await openProviders({ "GET /v1/connections": () => list(OLLAMA, LLAMACPP, openrouter({ ...NO_KEY, state })) });
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
    await user.click(within(ollama).getByRole("button", { name: "Edit Address" }));
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
    const card_ = card("OpenRouter");
    await user.click(within(card_).getByRole("button", { name: "Replace API key" }));
    await user.type(within(card_).getByLabelText("API key"), KEY);
    await user.click(within(card_).getByRole("button", { name: "Test" }));
    expect(await within(card_).findByText("unauthorised")).toBeInTheDocument();
    expect(server.find("POST", "/v1/connections/openrouter/test")[0]?.body).toEqual({ fields: { api_key: KEY } });
    expect(document.body.textContent).not.toContain(KEY);
  });

  it("tests the saved values with an empty body when nothing is typed", async () => {
    const { user, server } = await openProviders({ "POST /v1/connections/ollama/test": () => ({ status: "ok", reachable: true, reason: null }) });
    await user.click(within(card("Ollama")).getByRole("button", { name: "Test" }));
    expect(await within(card("Ollama")).findByText("Reachable")).toHaveAttribute("data-slot", "badge");
    expect(server.find("POST", "/v1/connections/ollama/test")[0]?.body).toEqual({ fields: {} });
  });

  it("stops testing a typed address after Cancel", async () => {
    const { user, server } = await openProviders({ "POST /v1/connections/ollama/test": () => ({ status: "ok", reachable: true, reason: null }) });
    const ollama = card("Ollama");
    await user.click(within(ollama).getByRole("button", { name: "Edit Address" }));
    await user.type(within(ollama).getByRole("textbox", { name: "Address" }), "x");
    await user.click(within(ollama).getByRole("button", { name: "Cancel" }));
    await user.click(within(ollama).getByRole("button", { name: "Test" }));
    expect(await within(ollama).findByText("Reachable")).toBeInTheDocument();
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

  it("shows the rule message when a save is refused with 400, in place of the generic line", async () => {
    const message = "The address must start with http:// or https://.";
    const { user } = await openProviders({ "PUT /v1/connections/ollama": () => json({ status: "error", message }, 400) });
    const ollama = card("Ollama");
    await user.click(within(ollama).getByRole("button", { name: "Edit Address" }));
    await user.type(within(ollama).getByRole("textbox", { name: "Address" }), "x");
    await user.click(within(ollama).getByRole("button", { name: "Save" }));
    expect(await within(ollama).findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByText(/could not complete/i)).toBeNull();
  });

  it("shows the conflict with a Reload action when omrs.jsonc changed on disk, and reads the cards again on Reload", async () => {
    const message = "omrs.jsonc changed on disk. Reload to see the new values.";
    const { user, server } = await openProviders({ "PUT /v1/connections/ollama": () => json({ status: "error", message }, 409) });
    const ollama = card("Ollama");
    await user.click(within(ollama).getByRole("button", { name: "Edit Address" }));
    await user.type(within(ollama).getByRole("textbox", { name: "Address" }), "x");
    await user.click(within(ollama).getByRole("button", { name: "Save" }));
    expect(await within(ollama).findByRole("alert")).toHaveTextContent(message);
    const reads = server.find("GET", "/v1/connections").length;
    await user.click(within(ollama).getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(server.find("GET", "/v1/connections").length).toBe(reads + 1));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the generic line for a failure that is not a refused value", async () => {
    const { user } = await openProviders({ "PUT /v1/connections/ollama": () => json({ status: "error", message: "boom at /srv/x" }, 500) });
    const ollama = card("Ollama");
    await user.click(within(ollama).getByRole("button", { name: "Edit Address" }));
    await user.type(within(ollama).getByRole("textbox", { name: "Address" }), "x");
    await user.click(within(ollama).getByRole("button", { name: "Save" }));
    expect(await within(ollama).findByRole("alert")).toHaveTextContent(/could not complete/i);
    expect(screen.queryByText(/\/srv\/x/)).toBeNull();
  });

  it("shows a friendly line with Retry when the providers cannot load", async () => {
    startApp("#/settings/providers", settingsServer({ "GET /v1/connections": () => json({ status: "error", message: "boom" }, 500) }));
    expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
