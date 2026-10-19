import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { json } from "../../test/fakeDocumentsServer";
import { openExperiments } from "../test/openExperiments";
import { ACTIVE_RUN, FAILED_EVENTS, FAILED_RESULT, FAILED_RUN, SECRET } from "../test/runFixtures";

const BASE = { runs: [FAILED_RUN, ACTIVE_RUN], results: { r1: FAILED_RESULT }, events: { r1: FAILED_EVENTS } };

function openRun(runId: string, initial: Parameters<typeof openExperiments>[0] = {}, extra: Parameters<typeof openExperiments>[1] = {}) {
  return openExperiments({ ...BASE, ...initial }, extra, `#/experiments/runs/${runId}`);
}

describe("run detail", () => {
  it("shows the run at its own address, with the status as text beside the heading", async () => {
    openRun("r1");
    expect(await screen.findByRole("heading", { level: 1, name: "Run r1" })).toBeInTheDocument();
    expect(await screen.findByText("Submitted from a saved revision")).toBeInTheDocument();
    expect(screen.getAllByText("failed").length).toBeGreaterThan(0);
  });

  it("shows the immutable snapshot of a failed run and its completed effects", async () => {
    openRun("r1");
    const snapshot = await screen.findByRole("region", { name: "Admitted snapshot" });
    expect(snapshot).toHaveTextContent("p1-r3");
    expect(snapshot).toHaveTextContent("sha256:abc123");
    expect(snapshot).toHaveTextContent("retrieve.dense@1");
    expect(snapshot).toHaveTextContent("What is RRF?");
    const effects = await screen.findByRole("region", { name: "Completed effects" });
    expect(effects).toHaveTextContent("source:a.md");
    expect(effects).toHaveTextContent(/committed before the run stopped/);
    expect(screen.queryByRole("button", { name: "Cancel run" })).not.toBeInTheDocument();
  });

  it("never renders a secret, only the server's redacted marker", async () => {
    const { container } = { container: document.body };
    openRun("r1");
    await screen.findByRole("region", { name: "Node outcomes" });
    expect(container.textContent).not.toContain(SECRET);
    expect(container.innerHTML).not.toContain(SECRET);
    expect(screen.getAllByText("[redacted]").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("region", { name: "Failure" })).toHaveTextContent("upstream refused Bearer [redacted]");
  });

  it("masks a secret the server let through in settings, in a failure and in a node error", async () => {
    const leaky = {
      ...FAILED_RUN,
      settings: { docs: { url: `https://user:${SECRET}@host/x?api_key=${SECRET}`, token: SECRET, nested: { password: SECRET } } },
      failure: { ...FAILED_RUN.failure, error: `refused Bearer ${SECRET}` },
    };
    const result = { ...FAILED_RESULT, nodes: [{ ...FAILED_RESULT.nodes![2]!, error: `denied ?token=${SECRET}` }], outputs: {} };
    const { user } = openRun("r1", { runs: [leaky], results: { r1: result } });
    const outcomes = await screen.findByRole("region", { name: "Node outcomes" });
    await user.click(within(outcomes).getByRole("button", { name: /^Inspect node answer/ }));
    expect(document.body.textContent).not.toContain(SECRET);
    expect(document.body.textContent).toContain("[redacted]");
  });

  it("shows node timings separately from the run wall time and never adds them up", async () => {
    const { user } = openRun("r1");
    const outcomes = await screen.findByRole("region", { name: "Node outcomes" });
    expect(await within(outcomes).findByRole("button", { name: /^Inspect node rerank/ })).toBeInTheDocument();
    expect(outcomes).toHaveTextContent("Run wall time: 2.50 s");
    expect(outcomes).toHaveTextContent(/not added up/);
    expect(outcomes).not.toHaveTextContent("3.15");
    await user.click(within(outcomes).getByRole("button", { name: /^Inspect node rerank/ }));
    const inspector = within(outcomes).getByRole("region", { name: "Node rerank" });
    expect(inspector).toHaveTextContent("Node time: 1.50 s");
    expect(inspector).toHaveTextContent("Fallback: reranker model unavailable");
    await user.click(within(outcomes).getByRole("button", { name: /^Inspect node answer/ }));
    expect(within(outcomes).getByRole("region", { name: "Node answer" })).toHaveTextContent("Error: TimeoutError: model");
  });

  it("retries only on an explicit click and opens the new run at its own address", async () => {
    const { server, user } = openRun("r1");
    await user.click(await screen.findByRole("button", { name: "Retry as a new run" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Run r9" })).toBeInTheDocument();
    expect(await screen.findByText("Retry of run r1")).toBeInTheDocument();
    expect(window.location.hash).toBe("#/experiments/runs/r9");
    expect(server.find("POST", "/v1/runs/r1/retry")).toHaveLength(1);
    expect(server.runs.get("r1")?.status).toBe("failed");
  });

  it("does not retry until the button is pressed", async () => {
    const { server } = openRun("r1");
    await screen.findByRole("button", { name: "Retry as a new run" });
    expect(server.calls.some((c) => c.path.endsWith("/retry"))).toBe(false);
  });

  it("offers cancel for an active run and labels it live, not replay", async () => {
    const { server, user } = openRun("r2", { events: { r2: [] } });
    const cancel = await screen.findByRole("button", { name: "Cancel run" });
    expect(screen.queryByRole("button", { name: "Retry as a new run" })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("region", { name: "Run progress" })).toHaveTextContent(/Live: polling/));
    expect(screen.queryByRole("region", { name: "Replay" })).not.toBeInTheDocument();
    await user.click(cancel);
    await waitFor(() => expect(server.find("POST", "/v1/runs/r2/cancel")).toHaveLength(1));
  });

  it("replays a finished run as labelled historical playback", async () => {
    const { user } = openRun("r1");
    const replay = await screen.findByRole("region", { name: "Replay" });
    expect(replay).toHaveTextContent("Replay of recorded events. Nothing runs again.");
    await waitFor(() => expect(replay).toHaveTextContent("Event 6 of 6"));
    expect(within(replay).getByText("answer").closest("li")).toHaveTextContent("Failed: TimeoutError: model");
    await user.click(within(replay).getByRole("button", { name: "Go to first event" }));
    expect(replay).toHaveTextContent("Event 1 of 6");
    expect(within(replay).getByText("answer").closest("li")).toHaveTextContent("Not started");
    await user.click(within(replay).getByRole("button", { name: "Next event" }));
    expect(replay).toHaveTextContent("Event 2 of 6: node_started (dense)");
    expect(within(replay).getByText("dense").closest("li")).toHaveTextContent("Running");
    expect(screen.queryByText(/Live:/)).not.toBeInTheDocument();
  });

  it("shows the evidence of a finished run", async () => {
    openRun("r1");
    const evidence = await screen.findByRole("region", { name: "Evidence" });
    expect(await within(evidence).findByRole("table", { name: "Ranked rows: reranked" })).toBeInTheDocument();
  });
});

describe("run address", () => {
  it("shows the detail for the run in the address after a reload", async () => {
    openRun("r2", { events: { r2: [] } });
    expect(await screen.findByRole("heading", { level: 1, name: "Run r2" })).toBeInTheDocument();
  });

  it("shows a not-found page with a link back when the server does not return the run", async () => {
    openRun("missing");
    expect(await screen.findByText('The run "missing" could not be found.')).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Experiments" })).toHaveAttribute("href", "#/experiments");
  });

  it("treats an unsafe run identifier as not found without calling the server for it", async () => {
    const { server } = openExperiments(BASE, {}, `#/experiments/runs/${encodeURIComponent("a b")}`);
    expect(await screen.findByText('The run "a b" could not be found.')).toBeInTheDocument();
    expect(server.calls.filter((c) => c.path.includes("a%20b") || c.path.includes("a b"))).toHaveLength(0);
  });

  it("shows one friendly line with Retry when the run cannot be read", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    openRun("r1", {}, { "GET /v1/runs/r1": () => json({ status: "error", message: "RAW boom" }, 500) });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("RAW boom");
  });
});
