import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { json } from "../../test/fakeDocumentsServer";
import { entry } from "../test/experimentsServer";
import { openExperiments } from "../test/openExperiments";
import { ACTIVE_RUN, experimentRun, FAILED_RUN } from "../test/runFixtures";

async function openRuns(initial: Parameters<typeof openExperiments>[0] = {}, extra: Parameters<typeof openExperiments>[1] = {}) {
  const opened = openExperiments({ runs: [FAILED_RUN, ACTIVE_RUN], ...initial }, extra);
  await opened.user.click(await screen.findByRole("button", { name: "Runs" }));
  return opened;
}

describe("runs list", () => {
  it("lists runs as links to their own addresses, with the status as text", async () => {
    await openRuns();
    const table = await screen.findByRole("table", { name: "Runs" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByRole("link", { name: "r1" })).toHaveAttribute("href", "#/experiments/runs/r1");
    expect(rows[0]).toHaveTextContent("failed");
    expect(rows[1]).toHaveTextContent("running");
  });

  it("filters by status through the run query", async () => {
    const { server, user } = await openRuns();
    await screen.findByRole("table", { name: "Runs" });
    const filter = screen.getByRole("group", { name: "Filter by status" });
    expect(within(filter).getByRole("button", { name: "All statuses" })).toHaveAttribute("aria-pressed", "true");
    await user.click(within(filter).getByRole("button", { name: "failed" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: "r2" })).not.toBeInTheDocument());
    expect(within(filter).getByRole("button", { name: "failed" })).toHaveAttribute("aria-pressed", "true");
    expect(server.calls.filter((c) => c.path.startsWith("/v1/runs?")).at(-1)?.path).toBe("/v1/runs?status=failed&limit=100");
  });

  it("reads the list again when Refresh list is pressed", async () => {
    const { server, user } = await openRuns();
    await screen.findByRole("table", { name: "Runs" });
    const before = server.find("GET", "/v1/runs?").length;
    await user.click(screen.getByRole("button", { name: "Refresh list" }));
    await waitFor(() => expect(server.find("GET", "/v1/runs?").length).toBe(before + 1));
  });

  it("shows the experiment context and index identity of an experiment run", async () => {
    await openRuns({ dirs: ["f"], entries: [entry("exp_1", "chunks", "active", "f/chunks")], runs: [experimentRun("run_exp", "exp_1"), experimentRun("run_live", null)] });
    const table = await screen.findByRole("table", { name: "Runs" });
    const [experiment, plain] = within(table).getAllByRole("row").slice(1);
    expect(experiment).toHaveTextContent("chunks (exp_1)");
    expect(experiment).toHaveTextContent("idx-exp_1");
    expect(plain).toHaveTextContent("None");
  });

  it("opens the run detail when a run link is followed, and lists it again from the back link", async () => {
    const { user } = await openRuns({ results: {}, events: {} });
    await user.click(await screen.findByRole("link", { name: "r1" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Run r1" })).toBeInTheDocument();
    expect(window.location.hash).toBe("#/experiments/runs/r1");
    await user.click(await screen.findByRole("link", { name: "Back to Experiments" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Experiments" })).toBeInTheDocument();
  });

  it("says no pipeline has run yet, with a link to Studio", async () => {
    await openRuns({ runs: [] });
    expect(await screen.findByText("No pipeline has run yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Studio" })).toHaveAttribute("href", "#/studio");
  });

  it("offers to show all statuses when a filter matches nothing", async () => {
    const { user } = await openRuns({ runs: [FAILED_RUN] });
    await screen.findByRole("table", { name: "Runs" });
    await user.click(screen.getByRole("button", { name: "succeeded" }));
    expect(await screen.findByText("No run has the status succeeded.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show all statuses" }));
    expect(await screen.findByRole("table", { name: "Runs" })).toBeInTheDocument();
  });

  it("shows one friendly line with Retry when the list fails, never the server text", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    await openRuns({}, { "GET /v1/runs": () => json({ status: "error", message: "RAW boom <html>" }, 500) });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("RAW boom");
  });
});
