import { act, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { event, FakeEventSource } from "../runs/test/fakes";
import { FINISH_HOLD_MS } from "../runs/useRecentlyFinished";
import { openSections, runPanel, TEMPLATE_PIPELINE, TEMPLATE_REVISION } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

function reducedMotion(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  reducedMotion(false);
});

afterEach(() => vi.unstubAllGlobals());

/** Opens the saved pipeline whose latest run the server reports as queued, and its event stream. */
async function openStream() {
  const run = { run_id: "run1", pipeline_id: "p1", revision_id: "p1-r1", status: "queued", last_sequence: 1 };
  const opened = openStudio("#/studio/search-copy/search", { pipelines: [TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION], runs: [run] });
  await waitFor(() => expect(opened.view.container.querySelectorAll("[data-slot='op-node']")).toHaveLength(4));
  await openSections(opened.user, "Revision and run");
  await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
  const source = FakeEventSource.latest();
  act(() => source.open());
  return { ...opened, source };
}

function nodeCard(nodeId: string): HTMLElement {
  const card = document.querySelector<HTMLElement>(`.react-flow__node[data-id="${nodeId}"] [data-slot='op-node']`);
  if (!card) throw new Error(`No canvas node ${nodeId}; rendered: ${document.querySelectorAll("[data-slot='op-node']").length} nodes`);
  return card;
}

function liveRegion() {
  return within(runPanel()).getByRole("region", { name: "Run progress" });
}

describe("canvas live run state", () => {
  it("shows only states that events report and no progress figures", async () => {
    const { source } = await openStream();
    expect(source.url).toBe("/v1/runs/run1/events/stream");
    act(() => {
      source.send(event(1, "run.status", { summary: { status: "running" } }));
      source.send(event(2, "node_completed", { node_id: "prepare" }));
      source.send(event(3, "node_started", { node_id: "dense" }));
      source.send(event(4, "node_progress", { node_id: "dense", summary: { message: "Read 40 rows", data: { done: 40 } } }));
    });
    await waitFor(() => expect(nodeCard("dense")).toHaveTextContent("Running"));
    expect(nodeCard("prepare")).toHaveTextContent("Completed");
    expect(nodeCard("rerank")).toHaveTextContent("Not started");
    expect(nodeCard("rerank")).not.toHaveTextContent(/Running|Completed/);
    expect(liveRegion()).toHaveTextContent("Live: streaming events");
    expect(liveRegion()).toHaveTextContent("Run run1: running");
    expect(runPanel().textContent).not.toMatch(/\d+\s*%|per second|remaining/i);
  });

  it("labels a fallback with its reason and a failure with its error", async () => {
    const { source } = await openStream();
    act(() => {
      source.send(event(1, "node_started", { node_id: "rerank" }));
      source.send(event(2, "node_fallback", { node_id: "rerank", summary: { message: "reranker model unavailable" } }));
      source.send(event(3, "node_completed", { node_id: "rerank" }));
      source.send(event(4, "node_failed", { node_id: "select", summary: { message: "ValueError: no rows" } }));
    });
    await waitFor(() => expect(nodeCard("rerank")).toHaveTextContent("Fallback: reranker model unavailable"));
    expect(nodeCard("select")).toHaveTextContent("Failed: ValueError: no rows");
  });

  it("shows a bypassed node with the reason the core gives", async () => {
    const { source } = await openStream();
    const message = "Disabled in the graph; passes its 'evidence' input through unchanged.";
    act(() => source.send(event(1, "node_bypassed", { node_id: "rerank", summary: { message, data: { reason: "disabled in the graph" } } })));
    await waitFor(() => expect(nodeCard("rerank")).toHaveTextContent(`Bypassed: ${message}`));
  });

  it("shows a reranker switched off by its node parameter as bypassed, not completed", async () => {
    const { source } = await openStream();
    act(() => {
      source.send(event(1, "node_started", { node_id: "rerank" }));
      source.send(event(2, "node_completed", { node_id: "rerank", summary: { data: { reranked: false, reason: "disabled by node parameter", rows: 3 } } }));
    });
    await waitFor(() => expect(nodeCard("rerank")).toHaveTextContent("Bypassed: disabled by node parameter"));
    expect(nodeCard("rerank")).not.toHaveTextContent("Completed");
  });

  it("re-reads the run record after each reconnect and shows its status", async () => {
    const { source, server } = await openStream();
    act(() => source.send(event(1, "run.status", { summary: { status: "running" } })));
    await waitFor(() => expect(liveRegion()).toHaveTextContent("Run run1: running"));
    const reads = () => server.calls.filter((c) => c.method === "GET" && c.path === "/v1/runs/run1").length;
    const before = reads();
    // The run changes while the connection is down; no event for it arrives.
    await server.fetchImpl("/v1/runs/run1/cancel", { method: "POST" });
    act(() => {
      source.fail(false);
      source.open();
    });
    await waitFor(() => expect(liveRegion()).toHaveTextContent("Run run1: cancelling"));
    expect(reads()).toBe(before + 1);
  });

  it("deduplicates events replayed after a reconnect", async () => {
    const { source } = await openStream();
    act(() => {
      source.send(event(1, "unit_started", { unit_id: "a.md" }));
      source.send(event(2, "unit_completed", { unit_id: "a.md" }));
      source.fail(false);
      source.open();
      source.send(event(2, "unit_completed", { unit_id: "a.md" }));
      source.send(event(3, "unit_started", { unit_id: "b.md" }));
    });
    await waitFor(() => expect(liveRegion()).toHaveTextContent("Units: 2 started, 1 completed, 0 failed, 0 cancelled"));
  });

  it("falls back to polling when the stream is refused and says so", async () => {
    const { source, server } = await openStream();
    act(() => source.fail(true));
    await waitFor(() => expect(liveRegion()).toHaveTextContent("Live: polling for events"));
    expect(server.calls.some((c) => c.path.startsWith("/v1/runs/run1/events?after_sequence=0"))).toBe(true);
  });

  it("highlights the edge into a running node, animated only without reduced motion", async () => {
    const { source, view } = await openStream();
    act(() => source.send(event(1, "node_started", { node_id: "dense" })));
    await new Promise((r) => setTimeout(r, 300));
    await waitFor(() => expect(view.container.querySelector(".flow-edge--active")).not.toBeNull());
    expect(view.container.querySelector(".flow-edge--active")).toHaveClass("animated");
  });

  it("draws every connection as a smooth-step line, not the default curve", async () => {
    const { view } = await openStream();
    await waitFor(() => expect(view.container.querySelectorAll(".react-flow__edge")).toHaveLength(3));
    const edges = [...view.container.querySelectorAll(".react-flow__edge")];
    for (const edge of edges) {
      expect(edge).toHaveClass("react-flow__edge-smoothstep");
      expect(edge).not.toHaveClass("react-flow__edge-default");
    }
  });

  it("animates the edge into a step that just finished, in the success style, and stops after the hold time", async () => {
    const { source, view } = await openStream();
    const edgeInto = () => view.container.querySelector(".flow-edge--done");
    act(() => source.send(event(1, "node_started", { node_id: "dense" })));
    await waitFor(() => expect(view.container.querySelector(".flow-edge--active")).not.toBeNull());
    act(() => source.send(event(2, "node_completed", { node_id: "dense" })));
    await waitFor(() => expect(edgeInto()).not.toBeNull());
    expect(edgeInto()).toHaveClass("animated");
    expect(view.container.querySelector(".flow-edge--active")).toBeNull();
    await waitFor(() => expect(edgeInto()).toBeNull(), { timeout: FINISH_HOLD_MS + 1500 });
  });

  it("does not animate an edge into a step that failed", async () => {
    const { source, view } = await openStream();
    act(() => source.send(event(1, "node_started", { node_id: "dense" })));
    act(() => source.send(event(2, "node_failed", { node_id: "dense", summary: { message: "No index." } })));
    await new Promise((r) => setTimeout(r, 300));
    expect(nodeCard("dense")).toHaveTextContent("Failed");
    expect(view.container.querySelector(".flow-edge--done")).toBeNull();
  });

  it("keeps a static highlight when reduced motion is requested", async () => {
    reducedMotion(true);
    const { source, view } = await openStream();
    act(() => source.send(event(1, "node_started", { node_id: "dense" })));
    await waitFor(() => expect(view.container.querySelector(".flow-edge--active")).not.toBeNull());
    expect(view.container.querySelector(".flow-edge--active")).not.toHaveClass("animated");
    expect(nodeCard("dense")).toHaveTextContent("Running");
  });
});
