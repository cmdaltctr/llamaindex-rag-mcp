import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { PREFERENCES_KEY } from "../lib/preferences";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { settingsServer } from "./test/fixtures";

const SECTIONS = ["Appearance", "Connections", "MCP", "Server log", "Runtime", "Workspace"];

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
  it("offers the six sections as chips in order and shows one at a time", async () => {
    await openSettings();
    const group = screen.getByRole("group", { name: "Sections" });
    expect(within(group).getAllByRole("button").map((button) => button.textContent)).toEqual(SECTIONS);
    expect(chip("Appearance")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getAllByRole("region")).toHaveLength(1);
    expect(screen.getByRole("region", { name: "Appearance" })).toBeInTheDocument();
  });

  it("shows only the selected section and marks its chip selected", async () => {
    const { user } = await openSettings();
    await user.click(chip("Server log"));
    expect(chip("Server log")).toHaveAttribute("aria-pressed", "true");
    expect(chip("Appearance")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("region", { name: "Server log" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Appearance" })).toBeNull();
    expect(window.location.hash).toBe("#/settings");
  });

  it("keeps the selected section out of the route", async () => {
    const { user } = await openSettings();
    await user.click(chip("Runtime"));
    expect(window.location.hash).toBe("#/settings");
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
    expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
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
    const { user } = await openSettings({ "GET /v1/health": () => ({ status: "ok", ready: false }) });
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
    expect(await within(workspace).findByText("/home/u/.omrg/workspace")).toBeInTheDocument();
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
    expect(within(workspace).getByText("/home/u/.omrg/workspace")).toBeInTheDocument();
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
