import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PluginState } from "../api/plugins";
import { json, type Handler } from "../test/fakeDocumentsServer";
import { CREDENTIAL_TOKEN, EDITOR_TOKEN, entry, INSTALL_HINT, MARIMO, TRUST, type ServerState } from "./test/experimentsServer";
import { openExperiments } from "./test/openExperiments";

const WITHOUT_PLUGIN = "The workspace works without the plugin.";

const STATES: PluginState[] = [
  MARIMO,
  { ...MARIMO, name: "old", display_name: "Old editor", status: "incompatible", launchable: false, message: "old 0.1 is below the tested range. Update it outside OMRG, then recheck." },
  { ...MARIMO, name: "fresh", display_name: null, status: "unchecked", launchable: false, message: "Recheck to probe the executable." },
  { ...MARIMO, name: "moved", display_name: null, status: "needs_approval", launchable: false, message: "The manifest changed. Register it again." },
  { ...MARIMO, name: "gone", display_name: null, status: "unavailable", launchable: false, message: "The executable is missing." },
];

async function openNotebooks(initial: Partial<ServerState> = {}, extra: Record<string, Handler> = {}) {
  const opened = openExperiments({ dirs: ["f"], entries: [entry("exp_1", "chunks", "active", "f/chunks")], plugins: [MARIMO], ...initial }, extra);
  await opened.user.click(await screen.findByRole("button", { name: "Notebooks" }));
  return opened;
}

const panel = (name: string) => screen.findByRole("region", { name });

afterEach(() => vi.restoreAllMocks());

describe("notebook plugins", () => {
  it("lists every plugin state with the server's detail and the trust notice", async () => {
    await openNotebooks({ plugins: STATES });
    const plugins = await panel("Plugins");
    const table = await within(plugins).findByRole("table", { name: "Registered plugins" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[1]!.textContent)).toEqual(["Compatible", "Incompatible", "Not checked", "Needs approval", "Unavailable"]);
    expect(rows[1]).toHaveTextContent("old 0.1 is below the tested range. Update it outside OMRG, then recheck.");
    expect(within(plugins).getByText(INSTALL_HINT)).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Trust notice" })).getByText(TRUST)).toBeInTheDocument();
  });

  it("registers only after the approval box is ticked", async () => {
    const { server, user } = await openNotebooks({ plugins: [] });
    const form = await screen.findByRole("form", { name: "Register a plugin" });
    await user.type(within(form).getByLabelText("Manifest path"), "/opt/omrg/plugins/marimo/manifest.json");
    await user.type(within(form).getByLabelText("Executable path"), "/home/u/.local/bin/marimo");
    const button = within(form).getByRole("button", { name: "Register plugin" });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(server.find("POST", "/v1/plugins")).toHaveLength(0);
    await user.click(within(form).getByRole("checkbox", { name: /I approve this manifest and executable/ }));
    await user.click(button);
    await waitFor(() => expect(server.find("POST", "/v1/plugins")).toHaveLength(1));
    expect(server.find("POST", "/v1/plugins")[0]!.body).toEqual({
      manifest_path: "/opt/omrg/plugins/marimo/manifest.json",
      executable_path: "/home/u/.local/bin/marimo",
      approved: true,
    });
    expect(await within(await panel("Plugins")).findByText("New editor (new)")).toBeInTheDocument();
    expect(await within(form).findByRole("status")).toHaveTextContent("Registered new: Not checked.");
  });

  it("shows a refused registration as one friendly line, not the server's text", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { user } = await openNotebooks({ plugins: [] }, { "POST /v1/plugins": () => json({ status: "error", message: "RAW The executable must be named 'marimo'." }, 400) });
    const form = await screen.findByRole("form", { name: "Register a plugin" });
    await user.type(within(form).getByLabelText("Manifest path"), "/m.json");
    await user.type(within(form).getByLabelText("Executable path"), "/usr/bin/python");
    await user.click(within(form).getByRole("checkbox", { name: /I approve/ }));
    await user.click(within(form).getByRole("button", { name: "Register plugin" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("The local server could not complete that request.");
    expect(document.body.textContent).not.toContain("RAW");
  });

  it("rechecks a plugin and shows the new detail", async () => {
    const { server, user } = await openNotebooks({ plugins: STATES });
    const table = await screen.findByRole("table", { name: "Registered plugins" });
    await user.click(within(table).getByRole("button", { name: "Recheck marimo" }));
    await waitFor(() => expect(server.find("POST", "/v1/plugins/marimo/recheck")).toHaveLength(1));
    expect(await within(table).findByText("marimo 0.25.2 is compatible")).toBeInTheDocument();
  });

  it("unregisters a plugin only after confirmation", async () => {
    const { server, user } = await openNotebooks({ plugins: STATES });
    const table = await screen.findByRole("table", { name: "Registered plugins" });
    await user.click(within(table).getByRole("button", { name: "Unregister old" }));
    expect(server.find("DELETE", "/v1/plugins/")).toHaveLength(0);
    await user.click(within(table).getByRole("button", { name: "Confirm unregister" }));
    await waitFor(() => expect(server.find("DELETE", "/v1/plugins/old")).toHaveLength(1));
    await waitFor(() => expect(within(table).queryByText("Old editor (old)")).toBeNull());
  });

  it("offers no install or update button and says the workspace works without a plugin", async () => {
    await openNotebooks({ plugins: [] });
    const editor = await panel("Notebook editor");
    expect(await within(editor).findByText(INSTALL_HINT)).toBeInTheDocument();
    expect(within(editor).getByText(WITHOUT_PLUGIN)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /install|update/i })).toBeNull();
    expect(within(editor).queryByRole("button", { name: "Open notebook editor" })).toBeNull();
  });

  it("keeps an incompatible plugin from opening an editor and shows its actionable message", async () => {
    const message = "marimo 0.27.0 is outside the tested range 0.25.0 to below 0.26.0. Install a tested version outside OMRG, then recheck.";
    await openNotebooks({ plugins: [{ ...MARIMO, status: "incompatible", launchable: false, version: "0.27.0", message }] });
    const editor = await panel("Notebook editor");
    expect(await within(editor).findByText(message)).toBeInTheDocument();
    expect(within(editor).getByText("Incompatible")).toBeInTheDocument();
    expect(within(editor).getByText(WITHOUT_PLUGIN)).toBeInTheDocument();
    expect(within(editor).queryByRole("button", { name: "Open notebook editor" })).toBeNull();
  });

  it("keeps the rest of the view working when the plugin routes fail", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    await openNotebooks({}, { "GET /v1/plugins": () => json({ status: "error", message: "RAW Session required." }, 403) });
    const plugins = await panel("Plugins");
    expect(await within(plugins).findByRole("alert")).toHaveTextContent(/workspace session was not accepted/);
    expect(document.body.textContent).not.toContain("RAW");
    expect(await panel("Notebook credential")).toBeInTheDocument();
  });
});

async function fillEditor(user: ReturnType<typeof userEvent.setup>) {
  const editor = await panel("Notebook editor");
  const form = await within(editor).findByRole("form", { name: "Open a notebook editor" });
  await waitFor(() => expect(within(form).getByRole("combobox", { name: "Experiment context" })).toHaveTextContent("chunks (exp_1)"));
  await user.type(within(form).getByLabelText("Notebook path"), "starter.py");
  return { editor, form };
}

describe("notebook editor", () => {
  it("needs explicit consent before it calls the open route", async () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    const { server, user } = await openNotebooks();
    const { form } = await fillEditor(user);
    const button = within(form).getByRole("button", { name: "Open notebook editor" });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(server.find("POST", "/v1/plugins/")).toHaveLength(0);
    await user.click(within(form).getByRole("checkbox", { name: /I trust this notebook/ }));
    await user.click(button);
    await waitFor(() => expect(server.find("POST", "/v1/plugins/marimo/editors")).toHaveLength(1));
    expect(server.find("POST", "/v1/plugins/marimo/editors")[0]!.body).toEqual({ notebook: "starter.py", experiment_context: "exp_1", consent: true });
  });

  it("opens the editor in a new tab with noopener and keeps the token out of the address and storage", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const { user } = await openNotebooks();
    const { editor, form } = await fillEditor(user);
    await user.click(within(form).getByRole("checkbox", { name: /I trust this notebook/ }));
    await user.click(within(form).getByRole("button", { name: "Open notebook editor" }));

    await waitFor(() => expect(open).toHaveBeenCalledTimes(1));
    const [url, target, features] = open.mock.calls[0]!;
    expect(url).toBe("http://127.0.0.1:2719/");
    expect(String(url)).not.toContain(EDITOR_TOKEN);
    expect(target).toBe("_blank");
    expect(String(features)).toContain("noopener");

    const secret = await within(editor).findByRole("region", { name: "Editor access token" });
    expect(within(secret).getByText(EDITOR_TOKEN)).toBeInTheDocument();
    expect(within(secret).getByText(/Shown once/)).toBeInTheDocument();
    const again = within(editor).getByRole("link", { name: "Open the editor tab again" });
    expect(again).toHaveAttribute("href", "http://127.0.0.1:2719/");
    expect(again).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(JSON.stringify({ ...window.localStorage, ...window.sessionStorage })).not.toContain(EDITOR_TOKEN);
    expect(document.querySelector("iframe, frame, embed, object")).toBeNull();
    expect(screen.getByText(TRUST)).toBeInTheDocument();
  });

  it("does not open a tab when the server address is not on this computer", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const remote = { status: "ok", launch_id: "launch_1", plugin: "marimo", notebook: "/n.py", experiment_context: "exp_1" };
    const { user } = await openNotebooks(
      {},
      {
        "POST /v1/plugins/marimo/editors": () =>
          json({ ...remote, url_without_token: "http://192.0.2.7:2719/", token_delivery: { method: "response_body_once", token: EDITOR_TOKEN }, trust_notice: TRUST }, 201),
      },
    );
    const { editor, form } = await fillEditor(user);
    await user.click(within(form).getByRole("checkbox", { name: /I trust this notebook/ }));
    await user.click(within(form).getByRole("button", { name: "Open notebook editor" }));
    expect(await within(editor).findByRole("alert")).toHaveTextContent(/not on this computer/);
    expect(open).not.toHaveBeenCalled();
    expect(screen.queryByText(EDITOR_TOKEN)).toBeNull();
  });

  it("lists running editors and stops one after confirmation", async () => {
    const running = { launch_id: "launch_1", plugin: "marimo", notebook: "/srv/exp/chunks/starter.py", experiment_context: "exp_1", url_without_token: "http://127.0.0.1:2719/" };
    const { server, user } = await openNotebooks({ editors: [running] });
    const list = await screen.findByRole("list", { name: "Running editors" });
    expect(await within(list).findByText("/srv/exp/chunks/starter.py")).toBeInTheDocument();
    await user.click(within(list).getByRole("button", { name: "Stop editor launch_1" }));
    expect(server.find("DELETE", "/v1/plugin-editors/")).toHaveLength(0);
    expect(within(list).getByText(/Notebook files are kept/)).toBeInTheDocument();
    await user.click(within(list).getByRole("button", { name: "Confirm stop" }));
    await waitFor(() => expect(server.find("DELETE", "/v1/plugin-editors/launch_1")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("list", { name: "Running editors" })).toBeNull());
  });
});

describe("notebook credential", () => {
  it("issues a bound credential and shows the token once, never in browser storage", async () => {
    const { server, user } = await openNotebooks();
    const credential = await panel("Notebook credential");
    await waitFor(() => expect(within(credential).getByRole("combobox", { name: "Context" })).toHaveTextContent("chunks (exp_1)"));
    await user.click(within(credential).getByRole("button", { name: "Issue credential" }));
    await waitFor(() => expect(server.find("POST", "/v1/credentials")).toHaveLength(1));
    expect(server.find("POST", "/v1/credentials")[0]!.body).toEqual({ scopes: ["graph", "read", "run"], label: "notebook", experiment_context: "exp_1" });

    const secret = await within(credential).findByRole("region", { name: "Credential token" });
    expect(within(secret).getByText(CREDENTIAL_TOKEN)).toBeInTheDocument();
    expect(within(secret).getByText(/Shown once/)).toBeInTheDocument();
    await user.click(within(secret).getByRole("button", { name: "Copy token" }));
    expect(await navigator.clipboard.readText()).toBe(CREDENTIAL_TOKEN);
    expect(await within(secret).findByText("Copied.")).toBeInTheDocument();
    expect(JSON.stringify({ ...window.localStorage })).not.toContain(CREDENTIAL_TOKEN);
    expect(JSON.stringify({ ...window.sessionStorage })).not.toContain(CREDENTIAL_TOKEN);

    await user.click(within(secret).getByRole("button", { name: "Hide token" }));
    expect(screen.queryByText(CREDENTIAL_TOKEN)).toBeNull();
    expect(document.body.textContent).not.toContain(CREDENTIAL_TOKEN);
  });

  it("asks for a sub-experiment first when no context exists", async () => {
    await openNotebooks({ entries: [] });
    const credential = await panel("Notebook credential");
    expect(await within(credential).findByText("Create a sub-experiment first.")).toBeInTheDocument();
    expect(within(credential).queryByRole("button", { name: "Issue credential" })).toBeNull();
  });
});
