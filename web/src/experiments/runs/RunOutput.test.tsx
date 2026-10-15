import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunEventRecord } from "../../api/runs";
import { event } from "../../runs/test/fakes";
import { openExperiments } from "../test/openExperiments";
import { ACTIVE_RUN, FAILED_EVENTS, FAILED_RESULT, FAILED_RUN } from "../test/runFixtures";

const BASE = { runs: [FAILED_RUN, ACTIVE_RUN], results: { r1: FAILED_RESULT }, events: { r1: FAILED_EVENTS } };
const LONG = "x".repeat(5000);

function openRun(runId: string, initial: Parameters<typeof openExperiments>[0] = {}, extra: Parameters<typeof openExperiments>[1] = {}) {
  return openExperiments({ ...BASE, ...initial }, extra, `#/experiments/runs/${runId}`);
}

function artefactCalls(server: ReturnType<typeof openRun>["server"]) {
  return server.calls.filter((call) => call.path.includes("/artefacts/"));
}

/** The failed run's events, with a status summary the server cut. */
function cutStatus(ref: string): RunEventRecord[] {
  return [...FAILED_EVENTS.slice(0, -1), event(6, "run.status", { summary: { status: "failed", wall_time_s: 2.5, truncated: true, artefact_ref: ref } })];
}

describe("full output of a cut status summary", () => {
  it("opens the status summary the server cut through the artefact route", async () => {
    const { server, user } = openRun("r1", { events: { r1: cutStatus("r1/status-failed.json") } }, {
      "GET /v1/runs/r1/artefacts/status-failed": () => ({ status: "ok", run_id: "r1", name: "status-failed", value: { status: "failed", error: "full error text" } }),
    });
    const replay = await screen.findByRole("region", { name: "Replay" });
    await waitFor(() => expect(replay).toHaveTextContent("The server cut this output."));
    expect(artefactCalls(server)).toHaveLength(0);
    await user.click(within(replay).getByRole("button", { name: "Open full output" }));
    const dialog = await screen.findByRole("dialog", { name: "Full output" });
    expect(await within(dialog).findByText(/"error": "full error text"/)).toBeInTheDocument();
    expect(artefactCalls(server).map((call) => call.path)).toEqual(["/v1/runs/r1/artefacts/status-failed"]);
  });

  it("shows a summary whose reference names another run as cut, with no action", async () => {
    const { server } = openRun("r1", { events: { r1: cutStatus("r2/status-failed.json") } });
    const replay = await screen.findByRole("region", { name: "Replay" });
    await waitFor(() => expect(replay).toHaveTextContent("The full output belongs to another run"));
    expect(within(replay).queryByRole("button", { name: "Open full output" })).toBeNull();
    expect(artefactCalls(server)).toHaveLength(0);
  });
});

describe("full output of a cut node summary", () => {
  it("opens a live node summary the server cut through the artefact route", async () => {
    const events = [
      event(1, "node_started", { run_id: "r2", node_id: "dense" }),
      event(2, "node_completed", { run_id: "r2", node_id: "dense", summary: { message: "done", data: { rows: [] }, truncated: true, artefact_ref: "r2/event-0a1b.json" } }),
    ];
    const { server, user } = openRun("r2", { events: { r2: events } }, {
      "GET /v1/runs/r2/artefacts/event-0a1b": () => ({ status: "ok", run_id: "r2", name: "event-0a1b", value: { message: "done", data: { rows: ["all rows"] } } }),
    });
    const outcomes = await screen.findByRole("region", { name: "Node outcomes" });
    await user.click(await within(outcomes).findByRole("button", { name: /^Inspect node dense/ }));
    const inspector = within(outcomes).getByRole("region", { name: "Node dense" });
    expect(await within(inspector).findByText("The server cut this output.")).toBeInTheDocument();
    await user.click(within(inspector).getByRole("button", { name: "Open full output" }));
    const dialog = await screen.findByRole("dialog", { name: "Full output" });
    expect(await within(dialog).findByText(/"all rows"/)).toBeInTheDocument();
    expect(artefactCalls(server).map((call) => call.path)).toEqual(["/v1/runs/r2/artefacts/event-0a1b"]);
  });

  it("opens a stored node summary the browser cut from memory", async () => {
    const nodes = FAILED_RESULT.nodes!.map((node) => (node.node_id === "dense" ? { ...node, summary: { note: LONG } } : node));
    const { server, user } = openRun("r1", { results: { r1: { ...FAILED_RESULT, nodes } } });
    const outcomes = await screen.findByRole("region", { name: "Node outcomes" });
    await user.click(await within(outcomes).findByRole("button", { name: /^Inspect node dense/ }));
    const inspector = within(outcomes).getByRole("region", { name: "Node dense" });
    await user.click(within(inspector).getByRole("button", { name: "Open full output" }));
    const dialog = await screen.findByRole("dialog", { name: "Full output" });
    expect(dialog.querySelector("pre")!.textContent).toContain(LONG);
    expect(artefactCalls(server)).toHaveLength(0);
  });
});

describe("full output of stored evidence", () => {
  it("opens a cut evidence row from memory", async () => {
    const { server, user } = openRun("r1");
    const table = await screen.findByRole("table", { name: "Ranked rows: reranked" });
    const row = within(table).getByText(/Preview cut at 4 KiB/).closest("tr")!;
    await user.click(within(row).getByRole("button", { name: "Open full output" }));
    const dialog = await screen.findByRole("dialog", { name: "Full output" });
    expect(dialog.querySelector("pre")!.textContent).toContain(`"text": "${"x".repeat(5000)}"`);
    expect(dialog).toHaveTextContent("run r1");
    expect(artefactCalls(server)).toHaveLength(0);
  });

  it("opens every row of a list longer than the preview", async () => {
    const { user } = openRun("r1");
    const evidence = await screen.findByRole("region", { name: "Evidence" });
    const note = await within(evidence).findByText("Showing the first 100 of 130 rows.");
    await user.click(within(note.parentElement!).getByRole("button", { name: "Open full output" }));
    const dialog = await screen.findByRole("dialog", { name: "Full output" });
    expect(dialog.querySelector("pre")!.textContent).toContain('"chunk_id": "f129"');
  });

  it("states that a long answer was cut and opens it in full", async () => {
    const outputs = { answer: { answer: `${"a".repeat(5000)} END`, citations: [] } };
    const { user } = openRun("r1", { results: { r1: { ...FAILED_RESULT, outputs } } });
    const evidence = await screen.findByRole("region", { name: "Evidence" });
    expect(await within(evidence).findByText(/Preview cut at 4 KiB/)).toBeInTheDocument();
    expect(evidence).not.toHaveTextContent("END");
    await user.click(within(evidence).getByRole("button", { name: "Open full output" }));
    const dialog = await screen.findByRole("dialog", { name: "Full output" });
    expect(dialog.querySelector("pre")!.textContent).toContain(" END");
  });

  it("opens a cut value of the admitted snapshot from memory", async () => {
    const { user } = openRun("r1", { runs: [{ ...FAILED_RUN, inputs: { query: `${LONG} TAIL` } }] });
    const snapshot = await screen.findByRole("region", { name: "Admitted snapshot" });
    expect(snapshot).not.toHaveTextContent("TAIL");
    await user.click(within(snapshot).getByRole("button", { name: "Open full output" }));
    const dialog = await screen.findByRole("dialog", { name: "Full output" });
    expect(dialog.querySelector("pre")!.textContent).toContain(" TAIL");
  });

  it("offers no action where nothing was cut", async () => {
    openRun("r1", { results: { r1: { ...FAILED_RESULT, outputs: { sparse: FAILED_RESULT.outputs!.sparse } } } });
    const evidence = await screen.findByRole("region", { name: "Evidence" });
    await within(evidence).findByRole("table", { name: "Ranked rows: sparse" });
    expect(screen.queryByRole("button", { name: "Open full output" })).toBeNull();
  });
});
