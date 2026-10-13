import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ExperimentsView } from "./ExperimentsView";
import { CREDENTIAL_TOKEN, entry, experimentsServer, run, TRUST, type ServerState } from "./test/experimentsServer";

function setup(initial: Partial<ServerState> = {}) {
  const server = experimentsServer(initial);
  const user = userEvent.setup();
  render(<ExperimentsView fetchImpl={server.fetchImpl} />);
  return { server, user };
}

function region(name: string) {
  return screen.getByRole("region", { name });
}

describe("Experiments view", () => {
  it("shows the server's trust notice verbatim and prominently", async () => {
    setup();
    const notice = await screen.findByRole("region", { name: "Trust notice" });
    await waitFor(() => expect(within(notice).getByText(TRUST)).toBeInTheDocument());
    expect(notice).toHaveClass("notice--warning");
  });

  it("lists contexts with their backend and index identity", async () => {
    setup({ entries: [entry("exp_1", "chunks"), entry("exp_2", "old", "revoked")] });
    const table = await screen.findByRole("table", { name: "Experiment contexts" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("chunks");
    expect(rows[0]).toHaveTextContent("Active");
    expect(rows[0]).toHaveTextContent("/srv/exp/chunks/output/lancedb");
    expect(rows[0]).toHaveTextContent("idx-exp_1");
    expect(rows[0]).toHaveTextContent("onnx / bge-small-en");
    expect(rows[1]).toHaveTextContent("Revoked");
    expect(within(rows[1]!).queryByRole("button")).toBeNull();
  });

  it("shows an empty state when no workspace is registered", async () => {
    setup();
    expect(await screen.findByTestId("empty-state")).toHaveTextContent("No experiment workspace is registered");
  });

  it("registers a folder relative to an approved root and sends the absolute path", async () => {
    const { server, user } = setup();
    const form = await screen.findByRole("region", { name: "Register an experiment workspace" });
    await within(form).findByRole("option", { name: "/srv/exp" });
    await user.type(within(form).getByLabelText("Folder inside the root"), "chunks");
    await user.type(within(form).getByLabelText("Name"), "chunks");
    await user.click(within(form).getByLabelText("Ingest into the experiment store"));
    await user.click(within(form).getByRole("button", { name: "Register workspace" }));
    await waitFor(() => expect(server.find("POST", "/v1/experiments")).toHaveLength(1));
    expect(server.find("POST", "/v1/experiments")[0]!.body).toEqual({ workspace: "/srv/exp/chunks", name: "chunks", actions: ["read"] });
    expect(await within(region("Experiment contexts")).findByText("chunks")).toBeInTheDocument();
  });

  it("refuses a folder that leaves the root before any request", async () => {
    const { server, user } = setup();
    const form = await screen.findByRole("region", { name: "Register an experiment workspace" });
    await within(form).findByRole("option", { name: "/srv/exp" });
    await user.type(within(form).getByLabelText("Folder inside the root"), "../elsewhere");
    await user.click(within(form).getByRole("button", { name: "Register workspace" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent(/inside the selected folder/);
    expect(server.find("POST", "/v1/experiments")).toHaveLength(0);
  });

  it("explains how to approve a root when the server has none", async () => {
    setup({ roots: [] });
    const form = await screen.findByRole("region", { name: "Register an experiment workspace" });
    expect(await within(form).findByText(/--experiment-root/)).toBeInTheDocument();
    expect(within(form).queryByRole("button", { name: "Register workspace" })).toBeNull();
  });

  it("revokes a context only after confirmation", async () => {
    const { server, user } = setup({ entries: [entry("exp_1", "chunks")] });
    const table = await screen.findByRole("table", { name: "Experiment contexts" });
    await user.click(within(table).getByRole("button", { name: "Revoke chunks" }));
    expect(server.find("DELETE", "/v1/experiments/")).toHaveLength(0);
    expect(within(table).getByText(/Workspace files are not touched/)).toBeInTheDocument();
    await user.click(within(table).getByRole("button", { name: "Keep context" }));
    expect(server.find("DELETE", "/v1/experiments/")).toHaveLength(0);

    await user.click(within(table).getByRole("button", { name: "Revoke chunks" }));
    await user.click(within(table).getByRole("button", { name: "Confirm revoke" }));
    await waitFor(() => expect(server.find("DELETE", "/v1/experiments/exp_1")).toHaveLength(1));
    expect(await within(table).findByText("Revoked")).toBeInTheDocument();
  });

  it("issues a bound credential and shows the token once, never in browser storage", async () => {
    const { server, user } = setup({ entries: [entry("exp_1", "chunks")] });
    const panel = await screen.findByRole("region", { name: "Notebook credential" });
    await within(panel).findByRole("option", { name: "chunks (exp_1)" });
    await user.click(within(panel).getByRole("button", { name: "Issue credential" }));
    await waitFor(() => expect(server.find("POST", "/v1/credentials")).toHaveLength(1));
    expect(server.find("POST", "/v1/credentials")[0]!.body).toEqual({ scopes: ["graph", "read", "run"], label: "notebook", experiment_context: "exp_1" });

    const secret = await within(panel).findByRole("region", { name: "Credential token" });
    expect(within(secret).getByText(CREDENTIAL_TOKEN)).toBeInTheDocument();
    expect(within(secret).getByText(/Shown once/)).toBeInTheDocument();
    await user.click(within(secret).getByRole("button", { name: "Copy token" }));
    expect(await navigator.clipboard.readText()).toBe(CREDENTIAL_TOKEN);
    expect(JSON.stringify({ ...window.localStorage })).not.toContain(CREDENTIAL_TOKEN);
    expect(JSON.stringify({ ...window.sessionStorage })).not.toContain(CREDENTIAL_TOKEN);

    await user.click(within(secret).getByRole("button", { name: "Hide token" }));
    expect(screen.queryByText(CREDENTIAL_TOKEN)).toBeNull();
  });

  it("lists experiment runs only and links into the Runs view", async () => {
    setup({ entries: [entry("exp_1", "chunks")], runs: [run("run_exp", "exp_1"), run("run_live", null)] });
    const runs = await screen.findByRole("region", { name: "Experiment runs" });
    expect(await within(runs).findByText("run_exp")).toBeInTheDocument();
    expect(within(runs).queryByText("run_live")).toBeNull();
    expect(within(runs).getByText("idx-exp_1")).toBeInTheDocument();
    expect(within(runs).getByRole("link", { name: "Open the Runs view" })).toHaveAttribute("href", "#/runs");
  });

  it("never embeds an editor frame", async () => {
    setup({ entries: [entry("exp_1", "chunks")] });
    await screen.findByRole("table", { name: "Experiment contexts" });
    expect(document.querySelector("iframe, frame, embed, object")).toBeNull();
  });
});
