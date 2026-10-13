import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { SettingsView } from "./SettingsView";

function setup(extra = {}) {
  const server = documentsServer({
    "GET /v1/health": () => ({ status: "ok", ready: true }),
    "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: ["files", "graph", "read", "run"], workspace: "/home/u/.omrg/workspace" }),
    "GET /v1/pipeline-operations": () => ({
      status: "ok",
      operations: [
        { operation_id: "retrieve.dense", title: "Dense retrieval", available: true, capabilities: [] },
        { operation_id: "rerank.cross_encoder", title: "Cross-encoder rerank", available: false, capabilities: ["reranker"] },
      ],
    }),
    "GET /v1/plugins": () => ({ status: "ok", plugins: [], editors: [], install_hint: "Install outside OMRG.", trust_notice: "Trust text." }),
    ...extra,
  });
  const onThemeChange = vi.fn();
  render(<SettingsView fetchImpl={server.fetchImpl} theme="system" onThemeChange={onThemeChange} />);
  return { server, onThemeChange, user: userEvent.setup() };
}

describe("Settings", () => {
  it("shows the workspace folder and the approved file roots", async () => {
    setup();
    expect(await screen.findByText("/home/u/.omrg/workspace")).toBeInTheDocument();
    const roots = screen.getByRole("table", { name: "File access" });
    const rows = within(roots).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("/srv/docs");
    expect(rows[0]).toHaveTextContent("Approved at launch");
    expect(rows[1]).toHaveTextContent("Managed uploads");
  });

  it("shows the workspace path from the session, not one derived from the uploads root", async () => {
    setup({
      "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: ["files"], workspace: "/data/omrg-workspace" }),
    });
    const workspace = await screen.findByRole("region", { name: "Workspace" });
    expect(await within(workspace).findByText("/data/omrg-workspace")).toBeInTheDocument();
    expect(within(workspace).queryByText("/home/u/.omrg/workspace")).toBeNull();
  });

  it("states when the session reports no workspace yet", async () => {
    setup({ "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: ["files"], workspace: null }) });
    const workspace = await screen.findByRole("region", { name: "Workspace" });
    expect(await within(workspace).findByText(/did not report the workspace folder/)).toBeInTheDocument();
  });

  it("shows runtime capabilities from the server", async () => {
    setup();
    const runtime = await screen.findByRole("region", { name: "Runtime" });
    expect(await within(runtime).findByText("Ready")).toBeInTheDocument();
    expect(within(runtime).getByText("files, graph, read, run")).toBeInTheDocument();
    expect(within(runtime).getByText("1 of 2 available")).toBeInTheDocument();
    expect(within(runtime).getByText(/Cross-encoder rerank/)).toBeInTheDocument();
  });

  it("reuses the theme control", async () => {
    const { user, onThemeChange } = setup();
    await user.selectOptions(screen.getByRole("combobox", { name: "Theme" }), "dark");
    expect(onThemeChange).toHaveBeenCalledWith("dark");
  });

  it("shows the plugin panel instead of a placeholder", async () => {
    setup();
    expect(await screen.findByRole("region", { name: "Plugins" })).toBeInTheDocument();
    expect(screen.queryByText("No plugin routes yet")).toBeNull();
  });

  it("offers no configuration or model switching outside the plugin panel", async () => {
    setup();
    await screen.findByText("/home/u/.omrg/workspace");
    const plugins = screen.getByRole("region", { name: "Plugins" });
    const outside = screen.queryAllByRole("textbox").filter((box) => !plugins.contains(box));
    expect(outside).toHaveLength(0);
    expect(screen.getAllByRole("combobox")).toHaveLength(1);
    expect(screen.getByText(/does not edit .env/)).toBeInTheDocument();
  });

  it("reports a section that could not load without hiding the rest", async () => {
    setup({ "GET /v1/roots": () => json({ status: "error", message: "Session required." }, 403) });
    expect(await screen.findByText(/Session required\./)).toBeInTheDocument();
    expect(await screen.findByText("Ready")).toBeInTheDocument();
  });
});
