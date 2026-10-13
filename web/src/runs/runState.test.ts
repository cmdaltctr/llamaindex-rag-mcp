import { describe, expect, it } from "vitest";
import { applyEvent, displayStatus, edgeRunStyle, EMPTY_RUN_VIEW, foldEvents, statusLabel, unitCounts } from "./runState";
import { event } from "./test/fakes";

describe("run state from events", () => {
  it("reports only what events report: a node without events has no state", () => {
    const view = foldEvents([event(1, "node_queued", { node_id: "dense" }), event(2, "node_started", { node_id: "dense" })]);
    expect(view.nodes.dense?.status).toBe("running");
    expect(view.nodes.rerank).toBeUndefined();
    expect(view.lastSequence).toBe(2);
  });

  it("never invents progress figures from progress events", () => {
    const view = foldEvents([
      event(1, "node_started", { node_id: "embed" }),
      event(2, "node_progress", { node_id: "embed", summary: { message: "Embedded batch 2", data: { done: 2, total: 5 } } }),
    ]);
    expect(view.nodes.embed?.status).toBe("running");
    expect(view.nodes.embed?.message).toBe("Embedded batch 2");
    expect(JSON.stringify(view)).not.toMatch(/percent|%|progress":\s*\d/);
  });

  it("records a fallback with its reason and a failure with its error", () => {
    const view = foldEvents([
      event(1, "node_started", { node_id: "rerank" }),
      event(2, "node_fallback", { node_id: "rerank", summary: { message: "reranker model unavailable" } }),
      event(3, "node_completed", { node_id: "rerank", summary: { data: { rows: 4, score_kind: "dense_similarity_v1" } } }),
      event(4, "node_started", { node_id: "answer" }),
      event(5, "node_failed", { node_id: "answer", summary: { message: "TimeoutError: model" } }),
      event(6, "node_skipped", { node_id: "cite", summary: { message: "Upstream node 'answer' did not complete." } }),
    ]);
    expect(view.nodes.rerank).toMatchObject({ status: "succeeded", fallback: "reranker model unavailable" });
    expect(displayStatus(view.nodes.rerank)).toBe("fallback");
    expect(view.nodes.rerank?.summary).toEqual({ rows: 4, score_kind: "dense_similarity_v1" });
    expect(view.nodes.answer).toMatchObject({ status: "failed", error: "TimeoutError: model" });
    expect(view.nodes.cite).toMatchObject({ status: "skipped", message: "Upstream node 'answer' did not complete." });
  });

  it("ignores an event whose sequence it has already applied", () => {
    const once = applyEvent(EMPTY_RUN_VIEW, event(1, "node_failed", { node_id: "dense", summary: { message: "boom" } }));
    const again = applyEvent(once, event(1, "node_completed", { node_id: "dense" }));
    expect(again).toBe(once);
  });

  it("counts units from unit events only", () => {
    const view = foldEvents([
      event(1, "unit_started", { unit_id: "a.md" }),
      event(2, "node_started", { node_id: "read", unit_id: "a.md" }),
      event(3, "unit_completed", { unit_id: "a.md" }),
      event(4, "unit_started", { unit_id: "b.md" }),
      event(5, "unit_failed", { unit_id: "b.md" }),
      event(6, "node_started", { node_id: "read", unit_id: "c.md" }),
    ]);
    expect(unitCounts(view)).toEqual({ started: 2, completed: 1, failed: 1, cancelled: 0 });
  });

  it("collects committed effects and the authoritative status event", () => {
    const view = foldEvents([
      event(1, "effect_committed", { node_id: "commit", unit_id: "a.md", summary: { data: { effect: "source:a" } } }),
      event(2, "effect_committed", { node_id: "commit", summary: { message: "source:b" } }),
      event(3, "run.status", { summary: { status: "cancelled", wall_time_s: 3.5, failed_node: null } }),
    ]);
    expect(view.effects).toEqual(["source:a", "source:b"]);
    expect(view.runStatus).toBe("cancelled");
    expect(view.wallTimeS).toBe(3.5);
  });

  it("labels states in words", () => {
    expect(statusLabel("succeeded")).toBe("Completed");
    expect(statusLabel("fallback")).toBe("Fallback");
    expect(statusLabel(null)).toBe("Not started");
  });
});

describe("edge highlighting", () => {
  it("highlights an edge only while its target node runs", () => {
    expect(edgeRunStyle("running", false)).toEqual({ animated: true, className: "flow-edge--active" });
    expect(edgeRunStyle("succeeded", false)).toEqual({ animated: false, className: undefined });
    expect(edgeRunStyle("queued", false)).toEqual({ animated: false, className: undefined });
    expect(edgeRunStyle(undefined, false)).toEqual({ animated: false, className: undefined });
  });

  it("uses a static highlight when motion is reduced", () => {
    expect(edgeRunStyle("running", true)).toEqual({ animated: false, className: "flow-edge--active" });
  });
});
