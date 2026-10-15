import { describe, expect, it } from "vitest";
import type { PipelineRecord, PipelineTemplate } from "../api/pipelines";
import { blankDraft, gridPositions, initialDraft, presetDraft, templateDraft } from "./drafts";
import { toDocument } from "./graph";
import { TEMPLATE_DOC, TEMPLATE_PIPELINE, TEMPLATE_REVISION } from "./test/helpers";

const SEARCH: PipelineTemplate = {
  name: "search",
  title: "Search",
  description: "Reproduces Engine.search.",
  standard_operation: "Engine.search",
  document: TEMPLATE_DOC,
  outputs: [],
};

function rerank(draft: ReturnType<typeof presetDraft>) {
  return draft.graph.nodes.find((node) => node.operation === "select.rerank");
}

describe("template and blank drafts", () => {
  it("lays a template out on a grid and keeps its wiring", () => {
    const draft = templateDraft(SEARCH);
    expect(draft.layout.title).toBe("Search");
    expect(draft.graph.edges).toEqual(TEMPLATE_DOC.edges);
    expect(draft.layout.positions.prepare).toEqual({ x: 40, y: 40 });
    expect(draft.layout.positions.dense).toEqual({ x: 300, y: 40 });
  });

  it("starts an empty graph with a title", () => {
    const draft = blankDraft("Empty pipeline");
    expect(draft.graph.nodes).toEqual([]);
    expect(draft.layout.title).toBe("Empty pipeline");
  });

  it("gives every node of a list a distinct slot", () => {
    const slots = Object.values(gridPositions(["a", "b", "c", "d", "e"]));
    expect(new Set(slots.map((slot) => `${slot.x},${slot.y}`)).size).toBe(5);
  });
});

describe("profile presets", () => {
  it("seeds the documents preset from the search template with rerank on", () => {
    const draft = presetDraft(SEARCH, "documents", "papers");
    expect(draft.graph.profile).toBe("documents");
    expect(draft.graph.collection).toBe("papers");
    expect(rerank(draft)?.params).toEqual({ enabled: true });
    expect(rerank(draft)?.enabled).not.toBe(false);
    expect(draft.graph.edges).toEqual(TEMPLATE_DOC.edges);
    expect(draft.layout.title).toBe("Documents search");
  });

  it("seeds the codebase preset with rerank off but the node still in the graph", () => {
    const draft = presetDraft(SEARCH, "codebase", "src");
    expect(draft.graph.profile).toBe("codebase");
    expect(draft.graph.collection).toBe("src");
    expect(rerank(draft)?.params).toEqual({ enabled: false });
    expect(draft.graph.nodes.map((node) => node.id)).toEqual(["prepare", "dense", "rerank", "select"]);
  });

  it("leaves the collection to the host default when none is chosen", () => {
    expect(presetDraft(SEARCH, "documents", null).graph.collection).toBeNull();
    expect(toDocument(presetDraft(SEARCH, "documents", null))).not.toHaveProperty("collection");
  });

  it("does not change the template it was built from", () => {
    presetDraft(SEARCH, "codebase", "src");
    expect(SEARCH.document.nodes.find((node) => node.id === "rerank")?.params).toEqual({});
  });
});

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
    expect(draft.layout.title).toBe("Fresh");
  });
});
