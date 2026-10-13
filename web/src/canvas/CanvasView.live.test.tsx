import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { event, FakeEventSource } from "../runs/test/fakes";
import { CanvasView } from "./CanvasView";
import { writeSession } from "./storage";
import { fakeServer } from "./test/fakeServer";
import { runPanel, TEMPLATE_DOC, TEMPLATE_PIPELINE, TEMPLATE_REVISION } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";

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
  writeSession({
    pipelineId: null,
    run: { runId: "run1", status: "queued", revisionId: "p1-r1", revisionNumber: 1, document: TEMPLATE_DOC },
  });
});

afterEach(() => vi.unstubAllGlobals());

async function openStream() {
  const server = fakeServer({ pipelines: [TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION] });
  const view = render(<CanvasView fetchImpl={server.fetchImpl} />);
  await userEvent.setup().selectOptions(await screen.findByLabelText("Pipeline"), "p1");
  await waitFor(() => expect(view.container.querySelectorAll(".op-node")).toHaveLength(4));
  await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
  const source = FakeEventSource.latest();
  act(() => source.open());
  return { server, source, view };
}

function nodeCard(nodeId: string): HTMLElement {
  const card = [...document.querySelectorAll<HTMLElement>(".op-node")].find((el) => el.querySelector(".op-node__id")?.textContent === nodeId);
  if (!card) throw new Error(`No canvas node ${nodeId}; rendered: ${document.querySelectorAll(".op-node").length} nodes, ${document.querySelectorAll(".react-flow__edge").length} edges`);
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
    await waitFor(() => expect(view.container.querySelector(".flow-edge--active")).not.toBeNull());
    expect(view.container.querySelector(".flow-edge--active")).toHaveClass("animated");
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
