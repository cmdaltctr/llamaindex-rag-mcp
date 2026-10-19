import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { json } from "../test/fakeDocumentsServer";
import { documentsServer } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { ConfigurationSection, ConfigurationView, groupSettings } from "./ConfigurationSection";
import type { ConfigurationState } from "./configurationTypes";

const KEY = "not-a-real-key-value-1234";

const STATE: ConfigurationState = {
  path: "~/.config/omrg/omrg.jsonc",
  revision: "r1",
  settings: [
    { key: "retrieval.top_k", value: 10, source: "default", applies: "restart", restart_pending: false },
    { key: "retrieval.reranker_enabled", value: false, source: "config-file", applies: "live", restart_pending: false },
    { key: "chunking.chunk_overlap", value: 100, source: "default", applies: "restart", restart_pending: false },
    { key: "ollama.address", value: "http://localhost:11434", source: "dotenv", applies: "live", restart_pending: false },
    { key: "openrouter.api_key", value: null, last4: "1234", source: "keychain", applies: "live", restart_pending: false },
    { key: "web_port", value: 8765, source: "default", applies: "restart", restart_pending: false },
  ],
  problems: [],
  handover: { pending: false, folder: null },
};

function view(state: ConfigurationState = STATE) {
  const onRestart = vi.fn();
  render(<ConfigurationView state={state} onRestart={onRestart} />);
  return { onRestart, user: userEvent.setup() };
}

describe("groupSettings", () => {
  it("groups by the text before the first dot and keeps the order of appearance", () => {
    const groups = groupSettings(STATE.settings);
    expect(groups.map((group) => group.name)).toEqual(["retrieval", "chunking", "ollama", "openrouter", "General"]);
    expect(groups[0]?.settings.map((setting) => setting.key)).toEqual(["retrieval.top_k", "retrieval.reranker_enabled"]);
    expect(groups[4]?.settings.map((setting) => setting.key)).toEqual(["web_port"]);
  });
});

describe("groupSettings with deeper keys", () => {
  it("uses only the text before the first dot", () => {
    const deep = { value: "x", source: "default", applies: "live" as const, restart_pending: false };
    const groups = groupSettings([{ key: "llamacpp.server.model", ...deep }, { key: "llamacpp.server.binary", ...deep }]);
    expect(groups.map((group) => group.name)).toEqual(["llamacpp"]);
  });
});

describe("ConfigurationView", () => {
  it("shows one table for each group with value and source words", () => {
    view();
    const retrieval = screen.getByRole("table", { name: "Retrieval" });
    const topK = within(retrieval).getByRole("row", { name: /retrieval\.top_k/ });
    expect(topK).toHaveTextContent("10");
    expect(topK).toHaveTextContent("default");
    expect(within(retrieval).getByRole("row", { name: /reranker_enabled/ })).toHaveTextContent("false");
    expect(within(retrieval).getByRole("row", { name: /reranker_enabled/ })).toHaveTextContent("from omrg.jsonc");
    expect(screen.getByRole("table", { name: "General" })).toHaveTextContent("web_port");
    expect(screen.getByRole("row", { name: /ollama\.address/ })).toHaveTextContent("Set in .env. Change it there.");
  });

  it("masks a key down to the last four characters", () => {
    view();
    const row = screen.getByRole("row", { name: /openrouter\.api_key/ });
    expect(row).toHaveTextContent("Key set · ending 1234");
    expect(row).toHaveTextContent("in system keychain");
    expect(document.body).not.toHaveTextContent(KEY);
  });

  it("says no key is set when a secret has no last four", () => {
    view({ ...STATE, settings: [{ key: "openrouter.api_key", value: null, last4: null, source: "none", applies: "live", restart_pending: false }] });
    expect(screen.getByRole("row", { name: /openrouter\.api_key/ })).toHaveTextContent("No key");
  });

  it("shows a short key as set without an ending, because the server sends an empty last four", () => {
    view({ ...STATE, settings: [{ key: "openrouter.api_key", value: null, last4: "", source: "keychain", applies: "live", restart_pending: false }] });
    const row = screen.getByRole("row", { name: /openrouter\.api_key/ });
    expect(row).toHaveTextContent("Key set");
    expect(row).not.toHaveTextContent("ending");
  });

  it("shows a setting with no value as not set", () => {
    view({ ...STATE, settings: [{ key: "answer.model", value: null, source: "default", applies: "live", restart_pending: false }] });
    expect(screen.getByRole("row", { name: /answer\.model/ })).toHaveTextContent("Not set");
  });

  it("shows the path with a copy action", () => {
    view();
    expect(screen.getByText("~/.config/omrg/omrg.jsonc")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy settings file path" })).toBeInTheDocument();
  });

  it("marks no row and offers no restart when nothing is pending", () => {
    view();
    expect(screen.queryByText("Restart to apply")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Restart/ })).not.toBeInTheDocument();
  });

  it("marks a pending row with Restart to apply and offers the restart dialog for it", async () => {
    const pending = STATE.settings.map((setting) => (setting.key === "retrieval.top_k" ? { ...setting, value: 10, source: "config-file", restart_pending: true } : setting));
    const { onRestart, user } = view({ ...STATE, settings: pending });
    expect(within(screen.getByRole("row", { name: /retrieval\.top_k/ })).getByText("Restart to apply")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /chunk_overlap/ })).queryByText("Restart to apply")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Restart…" }));
    expect(onRestart).toHaveBeenCalledWith({ change: "retrieval.top_k", plural: false });
  });

  it("names the count when several settings wait for a restart", async () => {
    const pending = STATE.settings.map((setting) => (setting.applies === "restart" ? { ...setting, restart_pending: true } : setting));
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
    const list = screen.getByRole("list", { name: "Problems in omrg.jsonc" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("retreival.top_k");
    expect(items[0]).toHaveTextContent("This key is not a setting. It is ignored.");
    expect(items[1]).toHaveTextContent("Enter a whole number from 1 to 100.");
  });

  it("shows no problem list when the file is clean", () => {
    view();
    expect(screen.queryByRole("list", { name: "Problems in omrg.jsonc" })).not.toBeInTheDocument();
  });

  it("tells the user when saved settings could not be moved", () => {
    view({ ...STATE, handover: { pending: true, folder: "~/.omrg/workspace" } });
    expect(screen.getByText("Saved settings could not be moved to omrg.jsonc")).toBeInTheDocument();
    expect(screen.getByText("~/.omrg/workspace")).toBeInTheDocument();
  });

  it("shows no handover line when nothing is pending", () => {
    view();
    expect(screen.queryByText(/could not be moved/)).not.toBeInTheDocument();
  });
});

describe("ConfigurationSection", () => {
  it("loads the configuration and opens the restart dialog for a pending change", async () => {
    const pending = { ...STATE, settings: STATE.settings.map((s) => (s.key === "web_port" ? { ...s, restart_pending: true } : s)) };
    const server = documentsServer({
      "GET /v1/settings/configuration": () => pending,
      "GET /v1/server/power": () => ({ managed: false }),
    });
    const user = userEvent.setup();
    renderWithProviders(<ConfigurationSection />, { fetchImpl: server.fetchImpl });
    expect(await screen.findByRole("table", { name: "General" })).toBeInTheDocument();
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
