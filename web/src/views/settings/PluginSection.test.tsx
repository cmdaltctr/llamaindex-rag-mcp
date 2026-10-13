import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { PluginState } from "../../api/plugins";
import { INSTALL_HINT, MARIMO, TRUST } from "../../experiments/test/experimentsServer";
import { documentsServer, json, type Handler } from "../test/fakeDocumentsServer";
import { PluginSection } from "./PluginSection";

const STATES: PluginState[] = [
  MARIMO,
  { ...MARIMO, name: "old", display_name: "Old editor", status: "incompatible", launchable: false, message: "old 0.1 is below the tested range. Update it outside OMRG, then recheck." },
  { ...MARIMO, name: "fresh", display_name: null, status: "unchecked", launchable: false, message: "Recheck to probe the executable." },
  { ...MARIMO, name: "moved", display_name: null, status: "needs_approval", launchable: false, message: "The manifest changed. Register it again." },
  { ...MARIMO, name: "gone", display_name: null, status: "unavailable", launchable: false, message: "The executable is missing." },
];

function setup(plugins: PluginState[] = STATES, extra: Record<string, Handler> = {}) {
  let current = plugins;
  const server = documentsServer({
    "GET /v1/plugins": () => ({ status: "ok", plugins: current, editors: [], install_hint: INSTALL_HINT, trust_notice: TRUST }),
    "POST /v1/plugins": () => {
      current = [...current, { ...MARIMO, name: "new", display_name: "New editor", status: "unchecked", message: "Recheck to probe the executable." }];
      return json({ status: "ok", plugin: current.at(-1), trust_notice: TRUST }, 201);
    },
    "POST /v1/plugins/marimo/recheck": () => ({ status: "ok", plugin: { ...MARIMO, message: "marimo 0.25.2 is compatible" } }),
    "DELETE /v1/plugins/old": () => {
      current = current.filter((p) => p.name !== "old");
      return { status: "ok", name: "old", unregistered: true };
    },
    ...extra,
  });
  render(<PluginSection fetchImpl={server.fetchImpl} />);
  return { server, user: userEvent.setup() };
}

function section() {
  return screen.getByRole("region", { name: "Plugins" });
}

describe("Settings plugin panel", () => {
  it("lists every plugin state with the server's detail", async () => {
    setup();
    const table = await within(section()).findByRole("table", { name: "Registered plugins" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[1]!.textContent)).toEqual([
      "Compatible",
      "Incompatible",
      "Not checked",
      "Needs approval",
      "Unavailable",
    ]);
    expect(rows[1]).toHaveTextContent("old 0.1 is below the tested range. Update it outside OMRG, then recheck.");
    expect(within(section()).getByText(TRUST)).toBeInTheDocument();
    expect(within(section()).getByText(INSTALL_HINT)).toBeInTheDocument();
    expect(screen.queryByText("No plugin routes yet")).toBeNull();
  });

  it("registers only after the approval box is ticked", async () => {
    const { server, user } = setup([]);
    const form = await within(section()).findByRole("form", { name: "Register a plugin" });
    await user.type(within(form).getByLabelText("Manifest path"), "/opt/omrg/plugins/marimo/manifest.json");
    await user.type(within(form).getByLabelText("Executable path"), "/home/u/.local/bin/marimo");
    const button = within(form).getByRole("button", { name: "Register plugin" });
    expect(button).toBeDisabled();
    await user.click(within(form).getByRole("checkbox", { name: /I approve this manifest and executable/ }));
    await user.click(button);
    await waitFor(() => expect(server.find("POST", "/v1/plugins")).toHaveLength(1));
    expect(server.find("POST", "/v1/plugins")[0]!.body).toEqual({
      manifest_path: "/opt/omrg/plugins/marimo/manifest.json",
      executable_path: "/home/u/.local/bin/marimo",
      approved: true,
    });
    expect(await within(section()).findByText("New editor (new)")).toBeInTheDocument();
  });

  it("shows a refused registration with the server's message", async () => {
    const { user } = setup([], { "POST /v1/plugins": () => json({ status: "error", message: "The executable must be named 'marimo', not 'python'." }, 400) });
    const form = await within(section()).findByRole("form", { name: "Register a plugin" });
    await user.type(within(form).getByLabelText("Manifest path"), "/m.json");
    await user.type(within(form).getByLabelText("Executable path"), "/usr/bin/python");
    await user.click(within(form).getByRole("checkbox", { name: /I approve/ }));
    await user.click(within(form).getByRole("button", { name: "Register plugin" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("The executable must be named 'marimo', not 'python'.");
  });

  it("rechecks a plugin and shows the new detail", async () => {
    const { server, user } = setup();
    const table = await within(section()).findByRole("table", { name: "Registered plugins" });
    await user.click(within(table).getByRole("button", { name: "Recheck marimo" }));
    await waitFor(() => expect(server.find("POST", "/v1/plugins/marimo/recheck")).toHaveLength(1));
    expect(await within(section()).findByText("marimo 0.25.2 is compatible")).toBeInTheDocument();
  });

  it("unregisters a plugin only after confirmation", async () => {
    const { server, user } = setup();
    const table = await within(section()).findByRole("table", { name: "Registered plugins" });
    await user.click(within(table).getByRole("button", { name: "Unregister old" }));
    expect(server.find("DELETE", "/v1/plugins/")).toHaveLength(0);
    await user.click(within(table).getByRole("button", { name: "Confirm unregister" }));
    await waitFor(() => expect(server.find("DELETE", "/v1/plugins/old")).toHaveLength(1));
    await waitFor(() => expect(within(section()).queryByText("Old editor (old)")).toBeNull());
  });

  it("states that the workspace works without a plugin and offers no install button", async () => {
    setup([]);
    expect(await within(section()).findByText(/No plugin is registered/)).toBeInTheDocument();
    expect(within(section()).getByText(/The workspace works without the plugin/)).toBeInTheDocument();
    expect(within(section()).queryByRole("button", { name: /install|update/i })).toBeNull();
  });
});
