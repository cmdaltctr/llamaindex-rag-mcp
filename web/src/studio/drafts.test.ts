import { describe, expect, it } from "vitest";
import type { PipelineRecord } from "../api/pipelines";
import { initialDraft } from "./drafts";
import { TEMPLATE_PIPELINE, TEMPLATE_REVISION } from "./test/helpers";

describe("initial draft of an opened pipeline", () => {
  it("uses the saved revision and layout", () => {
    const draft = initialDraft(TEMPLATE_PIPELINE, TEMPLATE_REVISION);
    expect(draft.graph.nodes).toHaveLength(4);
    expect(draft.layout.positions.dense).toEqual({ x: 240, y: 0 });
  });

  it("places nodes that the saved layout does not position", () => {
    const draft = initialDraft(TEMPLATE_PIPELINE, TEMPLATE_REVISION);
    const slots = Object.values(draft.layout.positions);
    expect(draft.layout.positions.rerank).toBeDefined();
    expect(new Set(slots.map((slot) => `${slot.x},${slot.y}`)).size).toBe(4);
  });

  it("opens an empty graph for a pipeline without a revision", () => {
    const pipeline: PipelineRecord = { ...TEMPLATE_PIPELINE, current_revision_id: null, layout: { title: "Fresh" } };
    const draft = initialDraft(pipeline, null);
    expect(draft.graph.nodes).toEqual([]);
    expect(draft.layout).not.toHaveProperty("title");
  });
});
