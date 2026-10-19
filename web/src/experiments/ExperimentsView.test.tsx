import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { json } from "../test/fakeDocumentsServer";
import { entry, TRUST, type ServerState } from "./test/experimentsServer";
import { openExperiments } from "./test/openExperiments";

const GROUPED: Partial<ServerState> = {
  dirs: ["reranker-calibration", "input-quality", "empty-one"],
  entries: [
    entry("exp_1", "run-a", "active", "reranker-calibration/run-a", ["chunk-size"]),
    entry("exp_2", "run-b", "active", "reranker-calibration/run-b"),
    entry("exp_3", "run-c", "active", "input-quality/run-c"),
  ],
};

describe("Experiments view", () => {
  it("has one h1, the shell sections as chips, and the server's trust notice verbatim", async () => {
    const { user } = openExperiments();
    expect(await screen.findByRole("heading", { level: 1, name: "Experiments" })).toBeInTheDocument();
    const notice = await screen.findByRole("region", { name: "Trust notice" });
    await waitFor(() => expect(within(notice).getByText(TRUST)).toBeInTheDocument());
    const sections = screen.getByRole("group", { name: "Sections" });
    expect(within(sections).getByRole("button", { name: "Experiments" })).toHaveAttribute("aria-pressed", "true");
    await user.click(within(sections).getByRole("button", { name: "Runs" }));
    expect(within(sections).getByRole("button", { name: "Runs" })).toHaveAttribute("aria-pressed", "true");
    expect(within(sections).getByRole("button", { name: "Experiments" })).toHaveAttribute("aria-pressed", "false");
  });

  it("groups contexts under their named folders", async () => {
    openExperiments(GROUPED);
    const calibration = await screen.findByRole("group", { name: "Folder reranker-calibration" });
    expect(within(calibration).getByText("run-a")).toBeInTheDocument();
    expect(within(calibration).getByText("run-b")).toBeInTheDocument();
    expect(within(calibration).queryByText("run-c")).toBeNull();
    const quality = screen.getByRole("group", { name: "Folder input-quality" });
    expect(within(quality).getByText("run-c")).toBeInTheDocument();
  });

  it("lists a folder that has no context with an empty indication", async () => {
    openExperiments(GROUPED);
    const empty = await screen.findByRole("group", { name: "Folder empty-one" });
    expect(within(empty).getByText(/Empty folder/)).toBeInTheDocument();
    const populated = screen.getByRole("group", { name: "Folder input-quality" });
    expect(within(populated).queryByText(/Empty folder/)).toBeNull();
  });

  it("shows the declared factors, status and backend identity of a sub-experiment", async () => {
    openExperiments({ ...GROUPED, entries: [...GROUPED.entries!, entry("exp_4", "old", "revoked", "input-quality/old")] });
    const calibration = await screen.findByRole("group", { name: "Folder reranker-calibration" });
    const row = within(calibration).getByRole("group", { name: "Experiment run-a" });
    expect(within(row).getByText("chunk-size")).toBeInTheDocument();
    expect(within(row).getByText("active")).toBeInTheDocument();
    expect(row).toHaveTextContent("/srv/exp/reranker-calibration/run-a/output/lancedb");
    expect(row).toHaveTextContent("idx-exp_1");
    expect(row).toHaveTextContent("onnx / bge-small-en");
    const old = screen.getByRole("group", { name: "Experiment old" });
    expect(within(old).getByText("revoked")).toBeInTheDocument();
    expect(within(old).queryByRole("button", { name: /Revoke/ })).toBeNull();
  });

  it("still lists a context the folder tree does not show", async () => {
    openExperiments({ entries: [entry("exp_9", "stray", "active", "stray")] }, { "GET /v1/experiments": () => ({ status: "ok", roots: ["/srv/exp"], folders: [{ root: "/srv/exp", tree: [] }], experiments: [entry("exp_9", "stray")], trust_notice: TRUST }) });
    expect(await screen.findByRole("group", { name: "Experiment stray" })).toBeInTheDocument();
  });

  it("states that no experiment root is approved and names the server flag, with no creation form", async () => {
    openExperiments({ roots: [] });
    const guidance = await screen.findByText(/No experiment root is approved/);
    expect(guidance.parentElement).toHaveTextContent("--experiment-root");
    expect(screen.getByText(/omrg web --experiment-root/, { selector: "code" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create folder" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Create sub-experiment" })).toBeNull();
  });

  it("revokes a context only after confirmation", async () => {
    const { server, user } = openExperiments({ dirs: ["f"], entries: [entry("exp_1", "chunks", "active", "f/chunks")] });
    const row = await screen.findByRole("group", { name: "Experiment chunks" });
    await user.click(within(row).getByRole("button", { name: "Revoke chunks" }));
    expect(server.find("DELETE", "/v1/experiments/")).toHaveLength(0);
    expect(within(row).getByText(/Workspace files are not touched/)).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Keep context" }));
    expect(server.find("DELETE", "/v1/experiments/")).toHaveLength(0);
    await user.click(within(row).getByRole("button", { name: "Revoke chunks" }));
    await user.click(within(row).getByRole("button", { name: "Confirm revoke" }));
    await waitFor(() => expect(server.find("DELETE", "/v1/experiments/exp_1")).toHaveLength(1));
    expect(await within(await screen.findByRole("group", { name: "Experiment chunks" })).findByText("revoked")).toBeInTheDocument();
  });

  it("shows one friendly line when the listing fails, never the server text", async () => {
    openExperiments({}, { "GET /v1/experiments": () => json({ status: "error", message: "RAW boom <html>" }, 500) });
    expect(await screen.findByRole("alert")).toHaveTextContent("The local server could not complete that request.");
    expect(document.body.textContent).not.toContain("RAW boom");
  });
});
