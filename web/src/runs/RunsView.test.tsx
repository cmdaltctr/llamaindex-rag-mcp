import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { RunsView } from "./RunsView";
import { ACTIVE_RUN, FAILED_RUN, runServer, SECRET } from "./test/runServer";

function setup(options: Parameters<typeof runServer>[0] = {}) {
  const server = runServer(options);
  const user = userEvent.setup();
  const view = render(<RunsView fetchImpl={server.fetchImpl} />);
  return { server, user, view };
}

async function openRun(user: ReturnType<typeof userEvent.setup>, runId: string) {
  await user.click(await screen.findByRole("button", { name: new RegExp(`^Run ${runId},`) }));
  return screen.findByRole("region", { name: `Run ${runId}` });
}

describe("Runs view", () => {
  it("lists runs and filters them by status", async () => {
    const { server, user } = setup();
    expect(await screen.findByRole("button", { name: /^Run r1, failed/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Run r2, running/ })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Status"), "failed");
    await waitFor(() => expect(screen.queryByRole("button", { name: /^Run r2,/ })).not.toBeInTheDocument());
    expect(server.calls.at(-1)?.path).toBe("/v1/runs?status=failed&limit=100");
  });

  it("shows the immutable snapshot of a failed run and its completed effects", async () => {
    const { user } = setup();
    const detail = await openRun(user, "r1");
    const snapshot = within(detail).getByRole("region", { name: "Admitted snapshot" });
    expect(snapshot).toHaveTextContent("p1-r3");
    expect(snapshot).toHaveTextContent("sha256:abc123");
    expect(snapshot).toHaveTextContent("retrieve.dense@1");
    expect(snapshot).toHaveTextContent("What is RRF?");
    const effects = within(detail).getByRole("region", { name: "Completed effects" });
    expect(effects).toHaveTextContent("source:a.md");
    expect(effects).toHaveTextContent(/committed before the run stopped/);
    expect(within(detail).queryByRole("button", { name: "Cancel run" })).not.toBeInTheDocument();
  });

  it("never renders a secret, only the server's redacted marker", async () => {
    const { user, view } = setup();
    const detail = await openRun(user, "r1");
    await within(detail).findByRole("region", { name: "Node outcomes" });
    expect(view.container.textContent).not.toContain(SECRET);
    expect(view.container.innerHTML).not.toContain(SECRET);
    expect(within(detail).getAllByText("[redacted]").length).toBeGreaterThanOrEqual(2);
    expect(detail).toHaveTextContent("upstream refused Bearer [redacted]");
  });

  it("shows node timings separately from the run wall time and never adds them up", async () => {
    const { user } = setup();
    const detail = await openRun(user, "r1");
    const outcomes = await within(detail).findByRole("region", { name: "Node outcomes" });
    expect(outcomes).toHaveTextContent("Run wall time: 2.50 s");
    expect(outcomes).toHaveTextContent(/not added up/);
    expect(outcomes).not.toHaveTextContent("3.15");
    await user.click(within(outcomes).getByRole("button", { name: /^Inspect node rerank/ }));
    const inspector = within(detail).getByRole("region", { name: "Node rerank" });
    expect(inspector).toHaveTextContent("Node time: 1.50 s");
    expect(inspector).toHaveTextContent("Fallback: reranker model unavailable");
    await user.click(within(outcomes).getByRole("button", { name: /^Inspect node answer/ }));
    expect(within(detail).getByRole("region", { name: "Node answer" })).toHaveTextContent("Error: TimeoutError: model");
  });

  it("retries only on an explicit click and opens the new run", async () => {
    const { server, user } = setup();
    const detail = await openRun(user, "r1");
    expect(server.calls.some((c) => c.path.endsWith("/retry"))).toBe(false);
    await user.click(within(detail).getByRole("button", { name: "Retry as a new run" }));
    const retried = await screen.findByRole("region", { name: "Run r9" });
    expect(retried).toHaveTextContent("Retry of run r1");
    expect(server.runs.get("r1")?.status).toBe("failed");
  });

  it("offers cancel for an active run and labels it live, not replay", async () => {
    const { server, user } = setup({ runs: [ACTIVE_RUN], events: { r2: [] } });
    const detail = await openRun(user, "r2");
    expect(within(detail).queryByRole("button", { name: "Retry as a new run" })).not.toBeInTheDocument();
    await waitFor(() => expect(within(detail).getByRole("region", { name: "Run progress" })).toHaveTextContent(/^.*Live: polling/));
    expect(within(detail).queryByRole("region", { name: "Replay" })).not.toBeInTheDocument();
    await user.click(within(detail).getByRole("button", { name: "Cancel run" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "POST" && c.path === "/v1/runs/r2/cancel")).toBe(true));
  });

  it("replays a finished run as labelled historical playback", async () => {
    const { user } = setup({ runs: [FAILED_RUN] });
    const detail = await openRun(user, "r1");
    const replay = await within(detail).findByRole("region", { name: "Replay" });
    expect(replay).toHaveTextContent("Replay of recorded events. Nothing runs again.");
    await waitFor(() => expect(replay).toHaveTextContent("Event 6 of 6"));
    expect(within(replay).getByText("answer").closest("li")).toHaveTextContent("Failed: TimeoutError: model");
    await user.click(within(replay).getByRole("button", { name: "Go to first event" }));
    expect(replay).toHaveTextContent("Event 1 of 6");
    expect(within(replay).getByText("answer").closest("li")).toHaveTextContent("Not started");
    await user.click(within(replay).getByRole("button", { name: "Next event" }));
    expect(replay).toHaveTextContent("Event 2 of 6: node_started (dense)");
    expect(within(replay).getByText("dense").closest("li")).toHaveTextContent("Running");
    expect(detail).not.toHaveTextContent(/Live:/);
  });
});
