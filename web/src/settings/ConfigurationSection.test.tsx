import { screen, waitFor, within } from "@testing-library/react";
import { createQueryClient } from "../api/queries";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { documentsServer, json, type Handler } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { ConfigurationSection, ConfigurationView, groupSettings } from "./ConfigurationSection";
import type { ConfigurationSetting, ConfigurationState } from "./configurationTypes";
import { IDENTITY_NOTE } from "./DocumentReadingSection";

const KEY = "not-a-real-key-value-1234";
const INSET = "[data-slot='card-inset']";
const SAVED = "Saved in settings (omrs.jsonc)";
const CONFLICT = "omrs.jsonc changed on disk. Reload to see the new values.";
const IDENTITY = "The embedding model is part of every collection. Change it in omrs.jsonc and re-ingest.";

/** A row the page may edit, from the default, applying after a restart. */
function setting(key: string, value: ConfigurationSetting["value"], overrides: Partial<ConfigurationSetting> = {}): ConfigurationSetting {
  return { key, value, source: "default", applies: "restart", restart_pending: false, saved: null, editable: true, read_only_reason: null, kind: "text", choices: null, min: null, max: null, nullable: false, ...overrides };
}

function readOnly(key: string, value: ConfigurationSetting["value"], reason: string, overrides: Partial<ConfigurationSetting> = {}): ConfigurationSetting {
  return setting(key, value, { editable: false, read_only_reason: reason, ...overrides });
}

const STATE: ConfigurationState = {
  path: "~/.config/omrs/omrs.jsonc",
  revision: "r1",
  settings: [
    setting("retrieval.top_k", 10, { kind: "int", min: 1, max: 100 }),
    setting("retrieval.reranker_enabled", false, { source: "config-file", applies: "live", kind: "bool" }),
    setting("chunking.chunk_overlap", 100, { kind: "int", min: 0 }),
    readOnly("ollama.address", "http://localhost:11434", "Remove OLLAMA__ADDRESS from the environment or .env to edit it here.", { source: "dotenv", applies: "live" }),
    readOnly("openrouter.api_key", null, "Keys are set on the provider cards as references.", { last4: "1234", source: "keychain", applies: "live", kind: null }),
    setting("web_port", 8765, { kind: "int", min: 1024, max: 65535 }),
  ],
  problems: [],
  handover: { pending: false, folder: null },
};

function withSettings(...settings: ConfigurationSetting[]): ConfigurationState {
  return { ...STATE, settings };
}

/** The mini card of one setting, found by its key. */
function rowOf(key: string): HTMLElement {
  const card = screen.getByText(key).closest(INSET);
  if (card === null) throw new Error(`no mini card for ${key}`);
  return card as HTMLElement;
}

function view(state: ConfigurationState = STATE, handlers: Record<string, Handler> = {}) {
  const onRestart = vi.fn();
  const server = documentsServer(handlers);
  renderWithProviders(<ConfigurationView state={state} onRestart={onRestart} />, { fetchImpl: server.fetchImpl });
  return { onRestart, server, user: userEvent.setup() };
}

/** Renders the whole section against a fake server that answers the save with `saved`. */
function section(state: ConfigurationState, saved: (body: Record<string, unknown>) => unknown) {
  const server = documentsServer({
    "GET /v1/settings/configuration": () => state,
    "PUT /v1/settings/configuration": saved,
    "GET /v1/server/power": () => ({ managed: false }),
  });
  renderWithProviders(<ConfigurationSection />, { fetchImpl: server.fetchImpl });
  return { server, user: userEvent.setup() };
}

describe("groupSettings", () => {
  it("groups by the text before the first dot and keeps the order of appearance", () => {
    const groups = groupSettings(STATE.settings);
    expect(groups.map((group) => group.name)).toEqual(["retrieval", "chunking", "ollama", "openrouter", "General"]);
    expect(groups[0]?.settings.map((s) => s.key)).toEqual(["retrieval.top_k", "retrieval.reranker_enabled"]);
    expect(groups[4]?.settings.map((s) => s.key)).toEqual(["web_port"]);
  });

  it("uses only the text before the first dot", () => {
    const groups = groupSettings([setting("llamacpp.server.model", "x"), setting("llamacpp.server.binary", "x")]);
    expect(groups.map((group) => group.name)).toEqual(["llamacpp"]);
  });
});

describe("ConfigurationView", () => {
  it("shows each setting as a mini card in its block card, with value and source words", () => {
    view();
    const retrieval = screen.getByRole("group", { name: "Retrieval" });
    expect(within(retrieval).getByText("retrieval.top_k").closest(INSET)).toHaveTextContent("10");
    expect(rowOf("retrieval.top_k")).toHaveTextContent("default");
    expect(rowOf("retrieval.reranker_enabled")).toHaveTextContent("Off");
    expect(rowOf("retrieval.reranker_enabled")).toHaveTextContent(SAVED);
    expect(within(screen.getByRole("group", { name: "General" })).getByText("web_port")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("offers Edit on an editable row", () => {
    view();
    expect(within(rowOf("retrieval.top_k")).getByRole("button", { name: "Edit retrieval.top_k" })).toBeInTheDocument();
  });

  it("makes a row set in .env read-only and names the variable to remove", () => {
    view();
    const row = rowOf("ollama.address");
    expect(row).toHaveTextContent("Set in .env. Change it there.");
    expect(row).toHaveTextContent("Remove OLLAMA__ADDRESS from the environment or .env to edit it here.");
    expect(within(row).queryByRole("button", { name: /^Edit/ })).not.toBeInTheDocument();
  });

  it("shows a read-only identity setting with its value and reason and no Edit", () => {
    view(withSettings(readOnly("embed_model", "nomic-embed-text", IDENTITY)));
    const row = rowOf("embed_model");
    expect(row).toHaveTextContent("nomic-embed-text");
    expect(row).toHaveTextContent(IDENTITY);
    expect(within(row).queryByRole("button")).not.toBeInTheDocument();
  });

  it("masks a key down to the last four characters and offers no Edit", () => {
    view();
    const row = rowOf("openrouter.api_key");
    expect(row).toHaveTextContent("Key set · ending 1234");
    expect(row).toHaveTextContent("in system keychain");
    expect(row).toHaveTextContent("Keys are set on the provider cards as references.");
    expect(within(row).queryByRole("button")).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(KEY);
  });

  it("says no key is set when a secret has no last four", () => {
    view(withSettings(readOnly("openrouter.api_key", null, "Keys are set on the provider cards as references.", { last4: null, source: "none" })));
    expect(rowOf("openrouter.api_key")).toHaveTextContent("No key");
  });

  it("shows a short key as set without an ending, because the server sends an empty last four", () => {
    view(withSettings(readOnly("openrouter.api_key", null, "Keys are set on the provider cards as references.", { last4: "", source: "keychain" })));
    const row = rowOf("openrouter.api_key");
    expect(row).toHaveTextContent("Key set");
    expect(row).not.toHaveTextContent("ending");
  });

  it("shows a setting with no value as not set", () => {
    view(withSettings(setting("answer.model", null)));
    expect(rowOf("answer.model")).toHaveTextContent("Not set");
  });

  it("shows a list setting as text with no Edit", () => {
    view(withSettings(readOnly("ingestion.ingest_extensions", [".md", ".pdf"], "Edit this in omrs.jsonc.", { kind: null })));
    const row = rowOf("ingestion.ingest_extensions");
    expect(row).toHaveTextContent('[".md",".pdf"]');
    expect(row).toHaveTextContent("Edit this in omrs.jsonc.");
    expect(within(row).queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows the index identity note in the Chunking card only", () => {
    view();
    expect(screen.getByRole("group", { name: "Chunking" })).toHaveTextContent(IDENTITY_NOTE);
    expect(screen.getByRole("group", { name: "Retrieval" })).not.toHaveTextContent(IDENTITY_NOTE);
  });

  it("shows the path with a copy action", () => {
    view();
    expect(screen.getByText("~/.config/omrs/omrs.jsonc")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy settings file path" })).toBeInTheDocument();
  });

  it("marks no row and offers no restart when nothing is pending", () => {
    view();
    expect(screen.queryByText("Restart to apply")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Restart/ })).not.toBeInTheDocument();
  });

  it("marks a pending row with Restart to apply and offers the restart dialog for it", async () => {
    const pending = STATE.settings.map((s) => (s.key === "retrieval.top_k" ? { ...s, source: "config-file", restart_pending: true } : s));
    const { onRestart, user } = view({ ...STATE, settings: pending });
    expect(within(rowOf("retrieval.top_k")).getByText("Restart to apply")).toBeInTheDocument();
    expect(within(rowOf("chunking.chunk_overlap")).queryByText("Restart to apply")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Restart…" }));
    expect(onRestart).toHaveBeenCalledWith({ change: "retrieval.top_k", plural: false });
  });

  it("names the count when several settings wait for a restart", async () => {
    const pending = STATE.settings.map((s) => (s.applies === "restart" ? { ...s, restart_pending: true } : s));
    const { onRestart, user } = view({ ...STATE, settings: pending });
    await user.click(screen.getByRole("button", { name: "Restart…" }));
    expect(onRestart).toHaveBeenCalledWith({ change: "3 changed settings", plural: true });
  });

  it("lists each problem by key with one plain line and no value", () => {
    view({
      ...STATE,
      problems: [
        { key: "retreival.top_k", kind: "unknown-key", message: "This key is not a setting. It is ignored." },
        { key: "retrieval.top_k", kind: "invalid-value", message: "Enter a whole number from 1 to 100." },
      ],
    });
    const items = within(screen.getByRole("list", { name: "Problems in omrs.jsonc" })).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("retreival.top_k");
    expect(items[0]).toHaveTextContent("This key is not a setting. It is ignored.");
    expect(items[1]).toHaveTextContent("Enter a whole number from 1 to 100.");
  });

  it("shows no problem list when the file is clean", () => {
    view();
    expect(screen.queryByRole("list", { name: "Problems in omrs.jsonc" })).not.toBeInTheDocument();
  });

  it("tells the user when saved settings could not be moved", () => {
    view({ ...STATE, handover: { pending: true, folder: "~/.omrs/workspace" } });
    expect(screen.getByText("Saved settings could not be moved to omrs.jsonc")).toBeInTheDocument();
    expect(screen.getByText("~/.omrs/workspace")).toBeInTheDocument();
  });

  it("shows no handover line when nothing is pending", () => {
    view();
    expect(screen.queryByText(/could not be moved/)).not.toBeInTheDocument();
  });
});

describe("Editing a Configuration setting", () => {
  it("sends a restart-only number with the revision it read, shows the saved row and offers the restart dialog", async () => {
    const { server, user } = section(STATE, () => ({
      status: "ok",
      ...STATE,
      revision: "r2",
      settings: STATE.settings.map((s) => (s.key === "retrieval.top_k" ? { ...s, value: 10, saved: 20, source: "config-file", restart_pending: true } : s)),
    }));
    await user.click(await screen.findByRole("button", { name: "Edit retrieval.top_k" }));
    const input = screen.getByRole("spinbutton", { name: "retrieval.top_k" });
    await user.clear(input);
    await user.type(input, "20");
    await user.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog", { name: "Restart to apply?" });
    expect(dialog).toHaveTextContent("retrieval.top_k applies after a restart.");
    expect(server.exact("PUT", "/v1/settings/configuration").map((call) => call.body)).toEqual([{ revision: "r1", changes: { "retrieval.top_k": 20 } }]);
    await user.click(within(dialog).getByRole("button", { name: "Later" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const row = rowOf("retrieval.top_k");
    expect(within(row).getByText("10")).toBeInTheDocument();
    expect(row).toHaveTextContent("Saved for the next launch: 20");
    expect(row).toHaveTextContent(SAVED);
    expect(within(row).getByText("Restart to apply")).toBeInTheDocument();
    expect(server.exact("GET", "/v1/settings/configuration")).toHaveLength(1);
  });

  it("turns a boolean off with the switch and shows Off", async () => {
    const enabled = setting("answer.enabled", true, { kind: "bool", applies: "live" });
    const { server, user } = section(withSettings(enabled), () => ({ status: "ok", ...withSettings({ ...enabled, value: false, source: "config-file" }), revision: "r2" }));
    await user.click(await screen.findByRole("button", { name: "Edit answer.enabled" }));
    await user.click(screen.getByRole("switch", { name: "answer.enabled" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(rowOf("answer.enabled")).toHaveTextContent("Off"));
    expect(server.exact("PUT", "/v1/settings/configuration")[0]?.body).toEqual({ revision: "r1", changes: { "answer.enabled": false } });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("edits a setting with fixed choices through a choice list and no free text", async () => {
    const mode = setting("metadata.extraction_mode", "fast", { kind: "choice", choices: ["disabled", "fast", "full"], applies: "live" });
    const { server, user } = section(withSettings(mode), () => ({ status: "ok", ...withSettings({ ...mode, value: "full", source: "config-file" }), revision: "r2" }));
    await user.click(await screen.findByRole("button", { name: "Edit metadata.extraction_mode" }));
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "metadata.extraction_mode" }));
    await user.click(await screen.findByRole("option", { name: "full" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.exact("PUT", "/v1/settings/configuration")).toHaveLength(1));
    expect(server.exact("PUT", "/v1/settings/configuration")[0]?.body).toEqual({ revision: "r1", changes: { "metadata.extraction_mode": "full" } });
  });

  it("refuses a number outside the range the server reports and sends no request", async () => {
    const rounds = setting("answer.max_rounds", 3, { kind: "int", min: 1, max: 8 });
    const { server, user } = section(withSettings(rounds), () => ({ status: "ok", ...withSettings(rounds) }));
    await user.click(await screen.findByRole("button", { name: "Edit answer.max_rounds" }));
    const input = screen.getByRole("spinbutton", { name: "answer.max_rounds" });
    await user.clear(input);
    await user.type(input, "12");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByText("Enter 1 to 8.")).toBeInTheDocument();
    expect(server.exact("PUT", "/v1/settings/configuration")).toHaveLength(0);
  });

  it("sends a decimal as a number", async () => {
    const threshold = setting("retrieval.rerank_threshold", 0.5, { kind: "float", min: 0, max: 1, applies: "live" });
    const { server, user } = section(withSettings(threshold), () => ({ status: "ok", ...withSettings({ ...threshold, value: 0.75, source: "config-file" }) }));
    await user.click(await screen.findByRole("button", { name: "Edit retrieval.rerank_threshold" }));
    const input = screen.getByRole("spinbutton", { name: "retrieval.rerank_threshold" });
    await user.clear(input);
    await user.type(input, "0.75");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.exact("PUT", "/v1/settings/configuration")).toHaveLength(1));
    expect(server.exact("PUT", "/v1/settings/configuration")[0]?.body).toEqual({ revision: "r1", changes: { "retrieval.rerank_threshold": 0.75 } });
  });

  it("clears an optional setting saved in the file, then shows the default", async () => {
    const timeout = setting("metadata.ollama_classify_timeout_override", 30, { kind: "float", source: "config-file", nullable: true, applies: "live", min: 0 });
    const { server, user } = section(withSettings(timeout), () => ({ status: "ok", ...withSettings({ ...timeout, value: null, source: "default" }), revision: "r2" }));
    await user.click(await screen.findByRole("button", { name: "Edit metadata.ollama_classify_timeout_override" }));
    await user.click(screen.getByRole("button", { name: "Clear" }));
    await waitFor(() => expect(rowOf("metadata.ollama_classify_timeout_override")).toHaveTextContent("Not set"));
    expect(rowOf("metadata.ollama_classify_timeout_override")).toHaveTextContent("default");
    expect(server.exact("PUT", "/v1/settings/configuration")[0]?.body).toEqual({ revision: "r1", changes: { "metadata.ollama_classify_timeout_override": null } });
  });

  it("offers no Clear on a setting that is not optional", async () => {
    view(withSettings(setting("retrieval.top_k", 20, { kind: "int", source: "config-file" })));
    await userEvent.setup().click(screen.getByRole("button", { name: "Edit retrieval.top_k" }));
    expect(screen.queryByRole("button", { name: "Clear" })).not.toBeInTheDocument();
  });

  it("offers no Clear on an optional setting that comes from the default", async () => {
    view(withSettings(setting("metadata.ollama_classify_timeout_override", null, { kind: "float", nullable: true })));
    await userEvent.setup().click(screen.getByRole("button", { name: "Edit metadata.ollama_classify_timeout_override" }));
    expect(screen.queryByRole("button", { name: "Clear" })).not.toBeInTheDocument();
  });

  it("adds the index identity note to the restart dialog after a chunking save", async () => {
    const overlap = setting("chunking.chunk_overlap", 100, { kind: "int", min: 0 });
    const { user } = section(withSettings(overlap), () => ({ status: "ok", ...withSettings({ ...overlap, source: "config-file", restart_pending: true }), revision: "r2" }));
    await user.click(await screen.findByRole("button", { name: "Edit chunking.chunk_overlap" }));
    const input = screen.getByRole("spinbutton", { name: "chunking.chunk_overlap" });
    await user.clear(input);
    await user.type(input, "50");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("dialog", { name: "Restart to apply?" })).toHaveTextContent(IDENTITY_NOTE);
  });

  it("shows the conflict line with Reload when omrs.jsonc changed on disk, and keeps the shown value", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { server, user } = section(STATE, () => json({ status: "error", message: CONFLICT }, 409));
    await user.click(await screen.findByRole("button", { name: "Edit retrieval.top_k" }));
    const input = screen.getByRole("spinbutton", { name: "retrieval.top_k" });
    await user.clear(input);
    await user.type(input, "20");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(CONFLICT);
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(server.exact("PUT", "/v1/settings/configuration")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(rowOf("retrieval.top_k")).toHaveTextContent("10");
    expect(rowOf("retrieval.top_k")).not.toHaveTextContent(SAVED);
  });
});

describe("A setting saved for the next launch", () => {
  it("shows the saved value next to Restart to apply and opens Edit filled with it", async () => {
    view(withSettings(setting("retrieval.top_k", 10, { kind: "int", min: 1, max: 100, saved: 20, source: "config-file", restart_pending: true })));
    const row = rowOf("retrieval.top_k");
    expect(within(row).getByText("10")).toBeInTheDocument();
    expect(row).toHaveTextContent("Saved for the next launch: 20");
    expect(within(row).getByText("Restart to apply")).toBeInTheDocument();
    await userEvent.setup().click(within(row).getByRole("button", { name: "Edit retrieval.top_k" }));
    expect(screen.getByRole("spinbutton", { name: "retrieval.top_k" })).toHaveValue(20);
  });

  it("names the default when a Clear waits for the restart", () => {
    view(withSettings(setting("metadata.ollama_classify_timeout_override", 30, { kind: "float", nullable: true, saved: null, source: "default", restart_pending: true })));
    expect(rowOf("metadata.ollama_classify_timeout_override")).toHaveTextContent("Saved for the next launch: default");
  });

  it("shows a saved boolean as On or Off", () => {
    view(withSettings(setting("answer.enabled", true, { kind: "bool", saved: false, source: "config-file", restart_pending: true })));
    expect(rowOf("answer.enabled")).toHaveTextContent("Saved for the next launch: Off");
  });

  it("shows no saved line when nothing waits for a restart", () => {
    view(withSettings(setting("retrieval.top_k", 20, { kind: "int", saved: 20, source: "config-file" })));
    expect(rowOf("retrieval.top_k")).not.toHaveTextContent("Saved for the next launch");
  });

  it("opens Edit filled with the value in force when the file holds no value", async () => {
    view(withSettings(setting("retrieval.top_k", 10, { kind: "int" })));
    await userEvent.setup().click(screen.getByRole("button", { name: "Edit retrieval.top_k" }));
    expect(screen.getByRole("spinbutton", { name: "retrieval.top_k" })).toHaveValue(10);
  });
});

describe("After a Configuration save", () => {
  it("marks the other settings reads stale and does not read the configuration again", async () => {
    const queryClient = createQueryClient({ retry: false });
    const others = [["connections"], ["mcp"], ["settings", "chat"], ["settings", "judge"], ["settings", "document-reading"], ["settings", "upload-limit"], ["settings", "web-port"], ["llamacpp-server"]];
    for (const queryKey of others) await queryClient.prefetchQuery({ queryKey, queryFn: () => ({}) });
    const enabled = setting("answer.enabled", true, { kind: "bool", applies: "live" });
    const server = documentsServer({
      "GET /v1/settings/configuration": () => withSettings(enabled),
      "PUT /v1/settings/configuration": () => ({ status: "ok", ...withSettings({ ...enabled, value: false, saved: false, source: "config-file" }), revision: "r2" }),
    });
    const user = userEvent.setup();
    renderWithProviders(<ConfigurationSection />, { fetchImpl: server.fetchImpl, queryClient });
    await user.click(await screen.findByRole("button", { name: "Edit answer.enabled" }));
    await user.click(screen.getByRole("switch", { name: "answer.enabled" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(rowOf("answer.enabled")).toHaveTextContent("Off"));
    for (const queryKey of others) expect(queryClient.getQueryState(queryKey)?.isInvalidated, queryKey.join("/")).toBe(true);
    expect(queryClient.getQueryState(["settings", "configuration"])?.isInvalidated).toBe(false);
    expect(server.exact("GET", "/v1/settings/configuration")).toHaveLength(1);
  });
});

describe("ConfigurationSection", () => {
  it("loads the configuration and opens the restart dialog for a pending change", async () => {
    const pending = { ...STATE, settings: STATE.settings.map((s) => (s.key === "web_port" ? { ...s, restart_pending: true } : s)) };
    const { user } = section(pending, () => pending);
    expect(await screen.findByRole("group", { name: "General" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Restart…" }));
    const dialog = await screen.findByRole("dialog", { name: "Restart to apply?" });
    expect(dialog).toHaveTextContent("web_port applies after a restart.");
    await user.click(within(dialog).getByRole("button", { name: "Later" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByText("Restart to apply")).toBeInTheDocument();
  });

  it("shows a friendly error with Retry when the request fails", async () => {
    const server = documentsServer({ "GET /v1/settings/configuration": () => json({ status: "error", message: "boom" }, 500) });
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    renderWithProviders(<ConfigurationSection />, { fetchImpl: server.fetchImpl });
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not complete/i);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
