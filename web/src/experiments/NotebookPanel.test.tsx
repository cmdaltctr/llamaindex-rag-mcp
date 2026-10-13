import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExperimentsView } from "./ExperimentsView";
import { json, type Handler } from "../views/test/fakeDocumentsServer";
import { EDITOR_TOKEN, entry, experimentsServer, INSTALL_HINT, MARIMO, TRUST, type ServerState } from "./test/experimentsServer";

const WITHOUT_PLUGIN = "The workspace works without the plugin.";

function setup(initial: Partial<ServerState> = {}, extra: Record<string, Handler> = {}) {
  const server = experimentsServer({ entries: [entry("exp_1", "chunks")], plugins: [MARIMO], ...initial }, extra);
  const user = userEvent.setup();
  const open = vi.spyOn(window, "open").mockReturnValue(null);
  render(<ExperimentsView fetchImpl={server.fetchImpl} />);
  return { server, user, open };
}

async function editorPanel() {
  return screen.findByRole("region", { name: "Notebook editor" });
}

afterEach(() => vi.restoreAllMocks());

describe("notebook editor", () => {
  it("needs explicit consent before it calls the open route", async () => {
    const { server, user } = setup();
    const panel = await editorPanel();
    await within(panel).findByRole("option", { name: "chunks (exp_1)" });
    await user.type(within(panel).getByLabelText("Notebook path"), "starter.py");
    const button = within(panel).getByRole("button", { name: "Open notebook editor" });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(server.find("POST", "/v1/plugins/")).toHaveLength(0);

    await user.click(within(panel).getByRole("checkbox", { name: /I trust this notebook/ }));
    await user.click(button);
    await waitFor(() => expect(server.find("POST", "/v1/plugins/marimo/editors")).toHaveLength(1));
    expect(server.find("POST", "/v1/plugins/marimo/editors")[0]!.body).toEqual({
      notebook: "starter.py",
      experiment_context: "exp_1",
      consent: true,
    });
  });

  it("opens the editor in a new tab with noopener and keeps the token out of the address and storage", async () => {
    const { user, open } = setup();
    const panel = await editorPanel();
    await within(panel).findByRole("option", { name: "chunks (exp_1)" });
    await user.type(within(panel).getByLabelText("Notebook path"), "starter.py");
    await user.click(within(panel).getByRole("checkbox", { name: /I trust this notebook/ }));
    await user.click(within(panel).getByRole("button", { name: "Open notebook editor" }));

    await waitFor(() => expect(open).toHaveBeenCalledTimes(1));
    const [url, target, features] = open.mock.calls[0]!;
    expect(url).toBe("http://127.0.0.1:2719/");
    expect(String(url)).not.toContain(EDITOR_TOKEN);
    expect(target).toBe("_blank");
    expect(String(features)).toContain("noopener");

    const secret = await within(panel).findByRole("region", { name: "Editor access token" });
    expect(within(secret).getByText(EDITOR_TOKEN)).toBeInTheDocument();
    expect(within(secret).getByText(/Shown once/)).toBeInTheDocument();
    const again = within(panel).getByRole("link", { name: "Open the editor tab again" });
    expect(again).toHaveAttribute("href", "http://127.0.0.1:2719/");
    expect(again).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(JSON.stringify({ ...window.localStorage, ...window.sessionStorage })).not.toContain(EDITOR_TOKEN);
    expect(document.querySelector("iframe, frame, embed, object")).toBeNull();
    expect(within(panel).getByText(TRUST)).toBeInTheDocument();
  });

  it("does not open a tab when the server address is not on this computer", async () => {
    const remote = { status: "ok", launch_id: "launch_1", plugin: "marimo", notebook: "/n.py", experiment_context: "exp_1" };
    const { user, open } = setup(
      {},
      {
        "POST /v1/plugins/marimo/editors": () =>
          json({ ...remote, url_without_token: "http://192.0.2.7:2719/", token_delivery: { method: "response_body_once", token: EDITOR_TOKEN }, trust_notice: TRUST }, 201),
      },
    );
    const panel = await editorPanel();
    await within(panel).findByRole("option", { name: "chunks (exp_1)" });
    await user.type(within(panel).getByLabelText("Notebook path"), "starter.py");
    await user.click(within(panel).getByRole("checkbox", { name: /I trust this notebook/ }));
    await user.click(within(panel).getByRole("button", { name: "Open notebook editor" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent(/not on this computer/);
    expect(open).not.toHaveBeenCalled();
    expect(screen.queryByText(EDITOR_TOKEN)).toBeNull();
  });

  it("lists running editors and stops one after confirmation", async () => {
    const editor = { launch_id: "launch_1", plugin: "marimo", notebook: "/srv/exp/chunks/starter.py", experiment_context: "exp_1", url_without_token: "http://127.0.0.1:2719/" };
    const { server, user } = setup({ editors: [editor] });
    const list = await screen.findByRole("list", { name: "Running editors" });
    expect(await within(list).findByText("/srv/exp/chunks/starter.py")).toBeInTheDocument();
    await user.click(within(list).getByRole("button", { name: "Stop editor launch_1" }));
    expect(within(list).getByText(/Notebook files are kept/)).toBeInTheDocument();
    await user.click(within(list).getByRole("button", { name: "Confirm stop" }));
    await waitFor(() => expect(server.find("DELETE", "/v1/plugin-editors/launch_1")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("list", { name: "Running editors" })).toBeNull());
  });

  it("explains how to install the plugin when none is registered, without an install button", async () => {
    setup({ plugins: [] });
    const panel = await editorPanel();
    expect(await within(panel).findByText(INSTALL_HINT)).toBeInTheDocument();
    expect(within(panel).getByText(WITHOUT_PLUGIN)).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: /install|update/i })).toBeNull();
    expect(within(panel).queryByRole("button", { name: "Open notebook editor" })).toBeNull();
  });

  it("shows the server's actionable message for an incompatible plugin", async () => {
    const message = "marimo 0.27.0 is outside the tested range 0.25.0 to below 0.26.0. Install a tested version outside OMRG, then recheck.";
    setup({ plugins: [{ ...MARIMO, status: "incompatible", launchable: false, version: "0.27.0", message }] });
    const panel = await editorPanel();
    expect(await within(panel).findByText(message)).toBeInTheDocument();
    expect(within(panel).getByText("Incompatible")).toBeInTheDocument();
    expect(within(panel).getByText(WITHOUT_PLUGIN)).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Open notebook editor" })).toBeNull();
  });

  it("keeps the rest of the view working when the plugin routes fail", async () => {
    setup({}, { "GET /v1/plugins": () => json({ status: "error", message: "Session required." }, 403) });
    const panel = await editorPanel();
    expect(await within(panel).findByText(/Session required\./)).toBeInTheDocument();
    expect(within(panel).getByText(WITHOUT_PLUGIN)).toBeInTheDocument();
    expect(await screen.findByRole("table", { name: "Experiment contexts" })).toBeInTheDocument();
  });
});
