import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { PREFERENCES_KEY } from "../lib/preferences";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { settingsServer } from "./test/fixtures";

const SECTIONS = ["Appearance", "Providers", "Chat", "MCP", "Server log", "Runtime", "Workspace", "Document reading", "Configuration"];

async function openSettings(handlers = {}) {
  const server = settingsServer(handlers);
  startApp("#/settings", server);
  await screen.findByRole("heading", { level: 1, name: "Settings" });
  return { server, user: userEvent.setup() };
}

function chip(name: string) {
  return screen.getByRole("button", { name });
}

describe("Settings sections", () => {
  it("offers the nine sections as chips in order and shows one at a time", async () => {
    await openSettings();
    const group = screen.getByRole("group", { name: "Sections" });
    expect(within(group).getAllByRole("button").map((button) => button.textContent)).toEqual(SECTIONS);
    expect(chip("Appearance")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getAllByRole("region")).toHaveLength(1);
    expect(screen.getByRole("region", { name: "Appearance" })).toBeInTheDocument();
  });

  it("shows only the selected section, marks its chip selected and writes its address", async () => {
    const { user } = await openSettings();
    await user.click(chip("Server log"));
    expect(chip("Server log")).toHaveAttribute("aria-pressed", "true");
    expect(chip("Appearance")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("region", { name: "Server log" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Appearance" })).toBeNull();
    expect(window.location.hash).toBe("#/settings/log");
  });

  it.each([
    ["Appearance", "#/settings/appearance"],
    ["Providers", "#/settings/providers"],
    ["Chat", "#/settings/chat"],
    ["MCP", "#/settings/mcp"],
    ["Server log", "#/settings/log"],
    ["Runtime", "#/settings/runtime"],
    ["Workspace", "#/settings/workspace"],
    ["Document reading", "#/settings/document-reading"],
    ["Configuration", "#/settings/configuration"],
  ])("writes %s to the address bar", async (name, hash) => {
    const { user } = await openSettings();
    await user.click(chip(name));
    expect(window.location.hash).toBe(hash);
  });

  it("opens Configuration from its address and lists the settings from the server", async () => {
    startApp(
      "#/settings/configuration",
      settingsServer({
        "GET /v1/settings/configuration": () => ({
          path: "/home/u/.config/omrs/omrs.jsonc",
          revision: "r1",
          settings: [{ key: "retrieval.top_k", value: 10, source: "default", applies: "restart", restart_pending: false }],
          problems: [],
          handover: { pending: false, folder: null },
        }),
      }),
    );
    expect(await screen.findByRole("region", { name: "Configuration" })).toBeInTheDocument();
    expect(chip("Configuration")).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText("retrieval.top_k")).toBeInTheDocument();
    expect(screen.getByText("/home/u/.config/omrs/omrs.jsonc")).toBeInTheDocument();
  });

  it("opens the section the address names", async () => {
    startApp("#/settings/runtime", settingsServer());
    expect(await screen.findByRole("region", { name: "Runtime" })).toBeInTheDocument();
    expect(chip("Runtime")).toHaveAttribute("aria-pressed", "true");
    expect(chip("Appearance")).toHaveAttribute("aria-pressed", "false");
  });

  it("goes back to the previous section with the Back button", async () => {
    const { user } = await openSettings();
    await user.click(chip("Runtime"));
    await user.click(chip("Workspace"));
    window.history.back();
    expect(await screen.findByRole("region", { name: "Runtime" })).toBeInTheDocument();
  });

  it("shows Home for a section that does not exist", async () => {
    startApp("#/settings/keys", settingsServer());
    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/home");
  });
});

describe("Appearance", () => {
  it("shows the stored theme and changes it", async () => {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ theme: "dark", lastCollection: null }));
    const { user } = await openSettings();
    const appearance = screen.getByRole("region", { name: "Appearance" });
    const select = within(appearance).getByRole("combobox", { name: "Theme" });
    expect(select).toHaveTextContent("Dark");
    await user.click(select);
    await user.click(await screen.findByRole("option", { name: "Light" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    const stored = JSON.parse(window.localStorage.getItem(PREFERENCES_KEY) ?? "{}") as { theme?: string };
    expect(stored.theme).toBe("light");
    expect(within(screen.getByText("Local workspace").closest("header")!).getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
  });
});

describe("Runtime", () => {
  it("shows readiness, session scopes and operation availability", async () => {
    const { user } = await openSettings();
    await user.click(chip("Runtime"));
    const runtime = screen.getByRole("region", { name: "Runtime" });
    expect(await within(runtime).findByText("Ready")).toBeInTheDocument();
    expect(within(runtime).getByText("files, graph, read, run")).toBeInTheDocument();
    expect(within(runtime).getByText("1 of 2 available")).toBeInTheDocument();
    expect(within(runtime).getByText(/Cross-encoder rerank/)).toBeInTheDocument();
  });

  it("says when the server is not ready", async () => {
    const { user } = await openSettings({ "GET /v1/health": () => ({ status: "ok", ready: false, version: "2.0.0" }) });
    await user.click(chip("Runtime"));
    expect(await screen.findByText("Starting or shutting down")).toBeInTheDocument();
  });

  it("reports a fact that could not load and still shows the others", async () => {
    const { user } = await openSettings({ "GET /v1/session": () => json({ status: "error", message: "Unexpected token <" }, 403) });
    await user.click(chip("Runtime"));
    const runtime = screen.getByRole("region", { name: "Runtime" });
    expect(await within(runtime).findByRole("alert")).toHaveTextContent(/session was not accepted/i);
    expect(within(runtime).getByText("Ready")).toBeInTheDocument();
    expect(screen.queryByText(/Unexpected token/)).toBeNull();
  });
});

describe("Workspace", () => {
  it("shows the workspace folder and the approved file roots", async () => {
    const { user } = await openSettings();
    await user.click(chip("Workspace"));
    const workspace = screen.getByRole("region", { name: "Workspace" });
    expect(await within(workspace).findByText("/home/u/.omrs/workspace")).toBeInTheDocument();
    const roots = await within(workspace).findByRole("table", { name: "File access" });
    const rows = within(roots).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("/srv/docs");
    expect(rows[0]).toHaveTextContent("Approved at launch");
    expect(rows[1]).toHaveTextContent("Managed uploads");
  });

  it("states when the session reports no workspace yet", async () => {
    const { user } = await openSettings({ "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: [], workspace: null }) });
    await user.click(chip("Workspace"));
    expect(await screen.findByText(/did not report the workspace folder/)).toBeInTheDocument();
  });

  it("shows a friendly line with Retry when the roots fail to load", async () => {
    const { user } = await openSettings({ "GET /v1/roots": () => json({ status: "error", message: "boom" }, 500) });
    await user.click(chip("Workspace"));
    const workspace = screen.getByRole("region", { name: "Workspace" });
    expect(await within(workspace).findByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(within(workspace).getByText("/home/u/.omrs/workspace")).toBeInTheDocument();
  });
});

describe("Moved controls", () => {
  it("has no plugin controls: they belong to Experiments", async () => {
    const { user, server } = await openSettings();
    for (const name of SECTIONS) await user.click(chip(name));
    expect(screen.queryByRole("region", { name: "Plugins" })).toBeNull();
    expect(screen.queryByText(/plugin/i)).toBeNull();
    expect(server.calls.some((call) => call.path.startsWith("/v1/plugins"))).toBe(false);
  });
});
