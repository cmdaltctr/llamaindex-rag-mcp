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
const SAVED = "Saved in settings (omrs.jsonc)";
const CONFLICT = "omrs.jsonc changed on disk. Reload to see the new values.";
const IDENTITY = "The embedding model is part of every collection. Change it in omrs.jsonc and re-ingest.";
const PUT = ["PUT", "/v1/settings/configuration"] as const;

/** A row the page may edit, from the default, applying after a restart. */
function setting(key: string, value: ConfigurationSetting["value"], overrides: Partial<ConfigurationSetting> = {}): ConfigurationSetting {
  return { key, value, source: "default", applies: "restart", restart_pending: false, saved: null, editable: true, read_only_reason: null, kind: "text", choices: null, min: null, max: null, nullable: false, ...overrides };
}

function readOnly(key: string, value: ConfigurationSetting["value"], reason: string, overrides: Partial<ConfigurationSetting> = {}): ConfigurationSetting {
  return setting(key, value, { editable: false, read_only_reason: reason, ...overrides });
}

const TOP_K = setting("retrieval.top_k", 10, { kind: "int", min: 1, max: 100 });

const STATE: ConfigurationState = {
  path: "~/.config/omrs/omrs.jsonc",
  revision: "r1",
  settings: [
    TOP_K,
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

/** The table row of one setting, found by its key. */
function rowOf(key: string): HTMLElement {
  const row = screen.getByText(key).closest("tr");
  if (row === null) throw new Error(`no table row for ${key}`);
  return row;
}

const cardOf = (block: string): HTMLElement => screen.getByRole("group", { name: block });

function view(state: ConfigurationState = STATE, handlers: Record<string, Handler> = {}) {
  const onRestart = vi.fn();
  const server = documentsServer(handlers);
  renderWithProviders(<ConfigurationView state={state} onRestart={onRestart} />, { fetchImpl: server.fetchImpl });
  return { onRestart, server, user: userEvent.setup() };
}

/** Renders the whole section against a fake server that answers a save with `saved`. */
function section(state: ConfigurationState, saved: (body: Record<string, unknown>) => unknown) {
  const server = documentsServer({
    "GET /v1/settings/configuration": () => state,
    "PUT /v1/settings/configuration": saved,
    "GET /v1/server/power": () => ({ managed: false }),
  });
  renderWithProviders(<ConfigurationSection />, { fetchImpl: server.fetchImpl });
  return { server, user: userEvent.setup() };
}

/** The listing after a save: revision r2, with the fields in `changes` changed for each key. */
function after(state: ConfigurationState, changes: Record<string, Partial<ConfigurationSetting>>): ConfigurationState {
  return { ...state, revision: "r2", settings: state.settings.map((s) => ({ ...s, ...changes[s.key] })) };
}

async function edit(user: ReturnType<typeof userEvent.setup>, block: string) {
  await user.click(await screen.findByRole("button", { name: `Edit ${block}` }));
}

async function typeInto(user: ReturnType<typeof userEvent.setup>, key: string, text: string) {
  const input = screen.getByRole("spinbutton", { name: key });
  await user.clear(input);
  if (text !== "") await user.type(input, text);
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

describe("A Configuration block", () => {
  it("Block shown as a table", () => {
    view();
    const table = within(cardOf("Retrieval")).getByRole("table", { name: "Retrieval" });
    expect(within(table).getAllByRole("columnheader").map((head) => head.textContent)).toEqual(["Setting", "Value", "Source"]);
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(rowOf("retrieval.top_k")).toHaveTextContent("10");
    expect(rowOf("retrieval.top_k")).toHaveTextContent("default");
    expect(rowOf("retrieval.reranker_enabled")).toHaveTextContent("Off");
    expect(rowOf("retrieval.reranker_enabled")).toHaveTextContent(SAVED);
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("Block with no editable setting", () => {
    view();
    expect(within(cardOf("Ollama")).queryByRole("button")).not.toBeInTheDocument();
    expect(within(cardOf("Openrouter")).queryByRole("button")).not.toBeInTheDocument();
    expect(within(cardOf("Retrieval")).getByRole("button", { name: "Edit Retrieval" })).toBeInTheDocument();
  });

  it("Read-only identity setting", async () => {
    const { user } = view(withSettings(readOnly("embed_model", "nomic-embed-text", IDENTITY), setting("web_port", 8765, { kind: "int" })));
    const lock = within(rowOf("embed_model")).getByRole("img", { name: IDENTITY });
    expect(lock).toHaveAttribute("title", IDENTITY);
    expect(screen.queryByText(IDENTITY)).not.toBeInTheDocument();
    await edit(user, "General");
    const row = rowOf("embed_model");
    expect(row).toHaveTextContent("nomic-embed-text");
    expect(within(row).getByRole("img", { name: IDENTITY })).toBeInTheDocument();
    expect(within(row).queryByRole("textbox")).not.toBeInTheDocument();
    expect(row.nextElementSibling).toHaveTextContent(IDENTITY);
    expect(screen.getByRole("spinbutton", { name: "web_port" })).toBeInTheDocument();
  });

  it("keeps a row set in .env as text and names the variable to remove in edit mode", async () => {
    const { user } = view(withSettings(STATE.settings[3]!, setting("ollama.model", "qwen")));
    expect(rowOf("ollama.address")).toHaveTextContent("Set in .env. Change it there.");
    await edit(user, "Ollama");
    expect(within(rowOf("ollama.address")).queryByRole("textbox")).not.toBeInTheDocument();
    expect(rowOf("ollama.address").nextElementSibling).toHaveTextContent("Remove OLLAMA__ADDRESS from the environment or .env to edit it here.");
  });

  it("masks a key down to the last four characters", () => {
    view();
    const row = rowOf("openrouter.api_key");
    expect(row).toHaveTextContent("Key set · ending 1234");
    expect(row).toHaveTextContent("in system keychain");
    expect(within(row).getByRole("img", { name: "Keys are set on the provider cards as references." })).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(KEY);
  });

  it("says no key or a short key set when the server sends no ending", () => {
    view(withSettings(readOnly("openrouter.api_key", null, "Keys are set on the provider cards.", { last4: null, source: "none", kind: null }), readOnly("anthropic.api_key", null, "Keys are set on the provider cards.", { last4: "", source: "keychain", kind: null })));
    expect(rowOf("openrouter.api_key")).toHaveTextContent("No key");
    expect(rowOf("anthropic.api_key")).toHaveTextContent("Key set");
    expect(rowOf("anthropic.api_key")).not.toHaveTextContent("ending");
  });

  it("shows a setting with no value as Not set and a list as text with a lock", () => {
    view(withSettings(setting("answer.model", null), readOnly("ingestion.ingest_extensions", [".md", ".pdf"], "Edit this in omrs.jsonc.", { kind: null })));
    expect(rowOf("answer.model")).toHaveTextContent("Not set");
    expect(rowOf("ingestion.ingest_extensions")).toHaveTextContent('[".md",".pdf"]');
    expect(within(rowOf("ingestion.ingest_extensions")).getByRole("img", { name: "Edit this in omrs.jsonc." })).toBeInTheDocument();
    expect(within(cardOf("Ingestion")).queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows the index identity note once, in the Chunking card only", () => {
    view(withSettings(STATE.settings[2]!, setting("chunking.chunk_size", 1024, { kind: "int" }), TOP_K));
    expect(within(cardOf("Chunking")).getAllByText(IDENTITY_NOTE)).toHaveLength(1);
    expect(cardOf("Retrieval")).not.toHaveTextContent(IDENTITY_NOTE);
  });

  it("Phone width", () => {
    view(withSettings({ ...TOP_K, source: "config-file", restart_pending: true, saved: 20 }));
    const [head] = within(screen.getByRole("table", { name: "Retrieval" })).getAllByRole("columnheader").slice(2);
    expect(head).toHaveClass("hidden", "sm:table-cell");
    const [setting, , source] = within(rowOf("retrieval.top_k")).getAllByRole("cell");
    expect(source).toHaveClass("hidden", "sm:table-cell");
    const under = within(setting!).getByText(SAVED).parentElement;
    expect(under).toHaveClass("sm:hidden");
    expect(under).toHaveTextContent("Restart to apply");
    expect(within(setting!).getByText("retrieval.top_k")).toHaveClass("[overflow-wrap:anywhere]");
  });
});

describe("A setting that waits for a restart", () => {
  it("Engine setting edited by hand", async () => {
    const pending = after(STATE, { "retrieval.top_k": { source: "config-file", restart_pending: true, saved: 20 } });
    const { onRestart, user } = view(pending);
    const row = rowOf("retrieval.top_k");
    expect(within(row).getByText("10")).toBeInTheDocument();
    expect(row).toHaveTextContent("Next launch: 20");
    expect(row).toHaveTextContent(SAVED);
    expect(within(row).getAllByText("Restart to apply").length).toBeGreaterThan(0);
    expect(rowOf("chunking.chunk_overlap")).not.toHaveTextContent("Restart to apply");
    await user.click(screen.getByRole("button", { name: "Restart…" }));
    expect(onRestart).toHaveBeenCalledWith({ change: "retrieval.top_k", plural: false });
  });

  it("opens Edit filled with the saved value", async () => {
    const { user } = view(withSettings({ ...TOP_K, source: "config-file", restart_pending: true, saved: 20 }));
    await edit(user, "Retrieval");
    expect(screen.getByRole("spinbutton", { name: "retrieval.top_k" })).toHaveValue(20);
  });

  it("names the default or On and Off as the next launch value", () => {
    view(withSettings(setting("metadata.timeout", 30, { kind: "float", nullable: true, restart_pending: true }), setting("answer.enabled", true, { kind: "bool", saved: false, source: "config-file", restart_pending: true })));
    expect(rowOf("metadata.timeout")).toHaveTextContent("Next launch: default");
    expect(rowOf("answer.enabled")).toHaveTextContent("Next launch: Off");
  });

  it("names the count when several settings wait for a restart", async () => {
    const { onRestart, user } = view({ ...STATE, settings: STATE.settings.map((s) => (s.applies === "restart" ? { ...s, restart_pending: true } : s)) });
    await user.click(screen.getByRole("button", { name: "Restart…" }));
    expect(onRestart).toHaveBeenCalledWith({ change: "3 changed settings", plural: true });
  });

  it("shows no next launch line when nothing waits for a restart", () => {
    view(withSettings(setting("retrieval.top_k", 20, { kind: "int", saved: 20, source: "config-file" })));
    expect(rowOf("retrieval.top_k")).not.toHaveTextContent("Next launch");
  });

  it("marks no row and offers no restart when nothing is pending", () => {
    view();
    expect(screen.queryByText("Restart to apply")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Restart/ })).not.toBeInTheDocument();
  });
});

describe("Editing a Configuration table", () => {
  it("Edit a restart-only number", async () => {
    const { server, user } = section(STATE, () => ({ status: "ok", ...after(STATE, { "retrieval.top_k": { saved: 20, source: "config-file", restart_pending: true } }) }));
    await edit(user, "Retrieval");
    await typeInto(user, "retrieval.top_k", "20");
    await user.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog", { name: "Restart to apply?" });
    expect(dialog).toHaveTextContent("retrieval.top_k applies after a restart.");
    expect(server.exact(...PUT).map((call) => call.body)).toEqual([{ revision: "r1", changes: { "retrieval.top_k": 20 } }]);
    await user.click(within(dialog).getByRole("button", { name: "Later" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
    const row = rowOf("retrieval.top_k");
    expect(within(row).getByText("10")).toBeInTheDocument();
    expect(row).toHaveTextContent("Next launch: 20");
    expect(row).toHaveTextContent(SAVED);
    expect(row).toHaveTextContent("Restart to apply");
    expect(server.exact("GET", "/v1/settings/configuration")).toHaveLength(1);
  });

  it("Several cells saved together", async () => {
    const hybrid = setting("retrieval.hybrid_enabled", false, { kind: "bool" });
    const state = withSettings(TOP_K, hybrid);
    const { server, user } = section(state, () => ({ status: "ok", ...after(state, { "retrieval.top_k": { saved: 20, restart_pending: true }, "retrieval.hybrid_enabled": { saved: true, restart_pending: true } }) }));
    await edit(user, "Retrieval");
    await typeInto(user, "retrieval.top_k", "20");
    await user.click(screen.getByRole("switch", { name: "retrieval.hybrid_enabled" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog", { name: "Restart to apply?" });
    expect(dialog).toHaveTextContent("2 changed settings apply after a restart.");
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(server.exact(...PUT).map((call) => call.body)).toEqual([{ revision: "r1", changes: { "retrieval.top_k": 20, "retrieval.hybrid_enabled": true } }]);
  });

  it("Nothing changed", async () => {
    const { server, user } = view();
    await edit(user, "Retrieval");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await typeInto(user, "retrieval.top_k", "20");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    await typeInto(user, "retrieval.top_k", "10");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(server.exact(...PUT)).toHaveLength(0);
  });

  it("Turn a boolean off", async () => {
    const enabled = setting("answer.enabled", true, { kind: "bool", applies: "live" });
    const { server, user } = section(withSettings(enabled), () => ({ status: "ok", ...after(withSettings(enabled), { "answer.enabled": { value: false, source: "config-file" } }) }));
    await edit(user, "Answer");
    await user.click(screen.getByRole("switch", { name: "answer.enabled" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(rowOf("answer.enabled")).toHaveTextContent("Off"));
    expect(server.exact(...PUT)[0]?.body).toEqual({ revision: "r1", changes: { "answer.enabled": false } });
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("Choose from fixed choices", async () => {
    const mode = setting("metadata.extraction_mode", "fast", { kind: "choice", choices: ["disabled", "fast", "full"], applies: "live" });
    const { server, user } = section(withSettings(mode), () => ({ status: "ok", ...after(withSettings(mode), { "metadata.extraction_mode": { value: "full", source: "config-file" } }) }));
    await edit(user, "Metadata");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "metadata.extraction_mode" }));
    await user.click(await screen.findByRole("option", { name: "full" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.exact(...PUT)).toHaveLength(1));
    expect(server.exact(...PUT)[0]?.body).toEqual({ revision: "r1", changes: { "metadata.extraction_mode": "full" } });
  });

  it("Out of range number refused before the request", async () => {
    const rounds = setting("answer.max_rounds", 3, { kind: "int", min: 1, max: 8 });
    const { server, user } = view(withSettings(rounds));
    await edit(user, "Answer");
    expect(screen.getByText("Enter 1 to 8.")).toHaveClass("text-muted-foreground");
    await typeInto(user, "answer.max_rounds", "12");
    expect(screen.getByText("Enter 1 to 8.")).toHaveClass("text-status-error-label");
    expect(screen.getByRole("spinbutton", { name: "answer.max_rounds" })).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(server.exact(...PUT)).toHaveLength(0);
  });

  it("asks for a value in an emptied text that is not optional", async () => {
    const { user } = view(withSettings(setting("answer.model", "qwen")));
    await edit(user, "Answer");
    await user.clear(screen.getByRole("textbox", { name: "answer.model" }));
    expect(screen.getByText("Enter a value.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("sends a decimal as a number", async () => {
    const threshold = setting("retrieval.rerank_threshold", 0.5, { kind: "float", min: 0, max: 1, applies: "live" });
    const { server, user } = section(withSettings(threshold), () => ({ status: "ok", ...after(withSettings(threshold), { "retrieval.rerank_threshold": { value: 0.75, source: "config-file" } }) }));
    await edit(user, "Retrieval");
    await typeInto(user, "retrieval.rerank_threshold", "0.75");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.exact(...PUT)).toHaveLength(1));
    expect(server.exact(...PUT)[0]?.body).toEqual({ revision: "r1", changes: { "retrieval.rerank_threshold": 0.75 } });
  });

  it("Cancel drops the changes", async () => {
    const { server, user } = view();
    await edit(user, "Retrieval");
    await typeInto(user, "retrieval.top_k", "20");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(within(rowOf("retrieval.top_k")).getByText("10")).toBeInTheDocument();
    await edit(user, "Retrieval");
    expect(screen.getByRole("spinbutton", { name: "retrieval.top_k" })).toHaveValue(10);
    expect(server.exact(...PUT)).toHaveLength(0);
  });

  it("Clear an optional setting", async () => {
    const timeout = setting("metadata.ollama_classify_timeout_override", 30, { kind: "float", source: "config-file", nullable: true, applies: "live", min: 0 });
    const { server, user } = section(withSettings(timeout), () => ({ status: "ok", ...after(withSettings(timeout), { [timeout.key]: { value: null, source: "default" } }) }));
    await edit(user, "Metadata");
    expect(screen.queryByRole("button", { name: "Clear" })).not.toBeInTheDocument();
    await typeInto(user, timeout.key, "");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(rowOf(timeout.key)).toHaveTextContent("Not set"));
    expect(rowOf(timeout.key)).toHaveTextContent("default");
    expect(server.exact(...PUT)[0]?.body).toEqual({ revision: "r1", changes: { [timeout.key]: null } });
  });

  it("adds the index identity note to the restart dialog after a chunking save", async () => {
    const overlap = setting("chunking.chunk_overlap", 100, { kind: "int", min: 0 });
    const { user } = section(withSettings(overlap), () => ({ status: "ok", ...after(withSettings(overlap), { [overlap.key]: { saved: 50, source: "config-file", restart_pending: true } }) }));
    await edit(user, "Chunking");
    await typeInto(user, overlap.key, "50");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("dialog", { name: "Restart to apply?" })).toHaveTextContent(IDENTITY_NOTE);
  });

  it("Refused save keeps the typed values", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { user } = section(STATE, () => json({ status: "error", message: "Enter a whole number from 1 to 50." }, 400));
    await edit(user, "Retrieval");
    await typeInto(user, "retrieval.top_k", "70");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await within(cardOf("Retrieval")).findByRole("alert")).toHaveTextContent("Enter a whole number from 1 to 50.");
    expect(screen.getByRole("spinbutton", { name: "retrieval.top_k" })).toHaveValue(70);
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });

  it("File changed under the page", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { server, user } = section(STATE, () => json({ status: "error", message: CONFLICT }, 409));
    await edit(user, "Retrieval");
    await typeInto(user, "retrieval.top_k", "20");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(CONFLICT);
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(server.exact(...PUT)).toHaveLength(1);
    expect(screen.getByRole("spinbutton", { name: "retrieval.top_k" })).toHaveValue(20);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(rowOf("retrieval.top_k")).toHaveTextContent("10");
    expect(rowOf("retrieval.top_k")).not.toHaveTextContent(SAVED);
  });
});

describe("One open table", () => {
  const BLOCKS = withSettings(TOP_K, setting("answer.enabled", true, { kind: "bool", applies: "live" }));

  it("switches at once when the open table has no changes", async () => {
    const { user } = view(BLOCKS);
    await edit(user, "Retrieval");
    await edit(user, "Answer");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "answer.enabled" })).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  it("Second table while the first has changes", async () => {
    const { user } = view(BLOCKS);
    await edit(user, "Retrieval");
    await typeInto(user, "retrieval.top_k", "20");
    await edit(user, "Answer");
    let dialog = await screen.findByRole("dialog", { name: "Discard your changes to Retrieval?" });
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Keep editing" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("spinbutton", { name: "retrieval.top_k" })).toHaveValue(20);
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    await edit(user, "Answer");
    dialog = await screen.findByRole("dialog", { name: "Discard your changes to Retrieval?" });
    await user.click(within(dialog).getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("switch", { name: "answer.enabled" })).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
    await edit(user, "Retrieval");
    expect(screen.getByRole("spinbutton", { name: "retrieval.top_k" })).toHaveValue(10);
  });
});

describe("The Settings file card", () => {
  it("shows the path with a copy action", () => {
    view();
    expect(screen.getByText("~/.config/omrs/omrs.jsonc")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy settings file path" })).toBeInTheDocument();
  });

  it("Problems listed", () => {
    const unknown = { key: "retreival.top_k", kind: "unknown-key", message: "This key is not a setting. It is ignored." };
    view({ ...STATE, problems: [unknown, { key: "retrieval.top_k", kind: "invalid-value", message: "Enter a whole number from 1 to 100." }] });
    const items = within(screen.getByRole("list", { name: "Problems in omrs.jsonc" })).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("retreival.top_k");
    expect(items[0]).toHaveTextContent("This key is not a setting. It is ignored.");
    expect(items[1]).toHaveTextContent("Enter a whole number from 1 to 100.");
  });


  it("Database rows not moved", () => {
    view({ ...STATE, handover: { pending: true, folder: "~/.omrs/workspace" } });
    expect(screen.getByText("Saved settings could not be moved to omrs.jsonc")).toBeInTheDocument();
    expect(screen.getByText("~/.omrs/workspace")).toBeInTheDocument();
  });

  it("shows no problem list and no handover line when the file is clean", () => {
    view();
    expect(screen.queryByRole("list", { name: "Problems in omrs.jsonc" })).not.toBeInTheDocument();
    expect(screen.queryByText(/could not be moved/)).not.toBeInTheDocument();
  });
});

describe("After a Configuration save", () => {
  it("marks the other settings reads stale and does not read the configuration again", async () => {
    const queryClient = createQueryClient({ retry: false });
    const others = [["connections"], ["mcp"], ["settings", "chat"], ["settings", "judge"], ["settings", "document-reading"], ["settings", "upload-limit"], ["settings", "web-port"], ["llamacpp-server"]];
    for (const queryKey of others) await queryClient.prefetchQuery({ queryKey, queryFn: () => ({}) });
    const enabled = setting("answer.enabled", true, { kind: "bool", applies: "live" });
    const saved = () => ({ status: "ok", ...withSettings({ ...enabled, value: false, saved: false, source: "config-file" }), revision: "r2" });
    const server = documentsServer({ "GET /v1/settings/configuration": () => withSettings(enabled), "PUT /v1/settings/configuration": saved });
    const user = userEvent.setup();
    renderWithProviders(<ConfigurationSection />, { fetchImpl: server.fetchImpl, queryClient });
    await edit(user, "Answer");
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
    expect(rowOf("web_port")).toHaveTextContent("Restart to apply");
  });

  it("shows a friendly error with Retry when the request fails", async () => {
    const server = documentsServer({ "GET /v1/settings/configuration": () => json({ status: "error", message: "boom" }, 500) });
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    renderWithProviders(<ConfigurationSection />, { fetchImpl: server.fetchImpl });
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not complete/i);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
