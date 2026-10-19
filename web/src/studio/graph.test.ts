import { describe, expect, it } from "vitest";
import {
  addEdge,
  addNode,
  edgeKey,
  emptyDraft,
  fromDocument,
  moveNode,
  removeEdge,
  removeNode,
  sameDocument,
  setEnabled,
  setParam,
  setSelection,
  setViewport,
  toDocument,
  toggleGraphInput,
  toggleGraphOutput,
  toLayout,
} from "./graph";
import { CATALOGUE } from "./test/catalogueFixture";

function op(id: string) {
  const found = CATALOGUE.find((entry) => entry.operation_id === id);
  if (found === undefined) throw new Error(id);
  return found;
}

function chain() {
  let draft = emptyDraft();
  for (const id of ["retrieve.prepare_query", "retrieve.dense", "select.rerank", "select.threshold"]) {
    draft = addNode(draft, op(id)).draft;
  }
  draft = addEdge(draft, { source: { node: "prepare_query", port: "query" }, target: { node: "dense", port: "query" } });
  draft = addEdge(draft, { source: { node: "dense", port: "evidence" }, target: { node: "rerank", port: "evidence" } });
  draft = addEdge(draft, { source: { node: "rerank", port: "evidence" }, target: { node: "threshold", port: "evidence" } });
  return draft;
}

describe("graph draft", () => {
  it("gives each added node a unique valid identifier and a position", () => {
    let draft = emptyDraft();
    const first = addNode(draft, op("retrieve.dense"));
    draft = first.draft;
    const second = addNode(draft, op("retrieve.dense"));
    expect(first.nodeId).toBe("dense");
    expect(second.nodeId).toBe("dense_2");
    expect(second.draft.layout.positions.dense_2).toBeDefined();
    expect(second.draft.graph.nodes.map((n) => n.version)).toEqual([1, 1]);
  });

  it("places an added node on a free grid slot, not on top of an existing node", () => {
    // A removed node leaves a gap, so the node count no longer names a free slot.
    let draft = chain();
    draft = removeNode(draft, "rerank");
    const added = addNode(draft, op("retrieve.sparse"));
    const taken = Object.entries(draft.layout.positions).map(([, at]) => at);
    const at = added.draft.layout.positions[added.nodeId];
    if (at === undefined) throw new Error("the added node has no position");
    for (const other of taken) {
      expect(Math.abs(other.x - at.x) >= 260 || Math.abs(other.y - at.y) >= 280).toBe(true);
    }
  });

  it("leaves 280 pixels between grid rows, so a tall step card does not cover the card below it", () => {
    let draft = emptyDraft();
    for (let index = 0; index < 5; index += 1) draft = addNode(draft, op("retrieve.dense")).draft;
    const ys = Object.values(draft.layout.positions).map((at) => at.y);
    expect(Math.max(...ys) - Math.min(...ys)).toBe(280);
  });

  it("serialises the execution document without layout data", () => {
    const doc = toDocument(chain());
    expect(doc.schema_version).toBe(1);
    expect(doc.nodes.map((n) => n.id)).toEqual(["prepare_query", "dense", "rerank", "threshold"]);
    expect(JSON.stringify(doc)).not.toContain("positions");
    expect(JSON.stringify(doc)).not.toContain("Search");
    expect(toLayout(chain())).not.toHaveProperty("title");
    expect(Object.keys(toLayout(chain())).sort()).toEqual(["direction", "positions", "selection", "viewport"]);
  });

  it("changes only the layout when a node moves, the viewport changes or the selection changes", () => {
    const draft = chain();
    let moved = moveNode(draft, "dense", { x: 900, y: 12 });
    moved = setViewport(moved, { x: 5, y: 6, zoom: 1.5 });
    moved = setSelection(moved, ["dense"]);
    expect(toDocument(moved)).toEqual(toDocument(draft));
    expect(toLayout(moved).positions?.dense).toEqual({ x: 900, y: 12 });
    expect(toLayout(moved).viewport).toEqual({ x: 5, y: 6, zoom: 1.5 });
    expect(toLayout(moved).selection).toEqual(["dense"]);
  });

  it("rewires the saved document when edges change", () => {
    let draft = chain();
    draft = removeEdge(draft, "dense.evidence->rerank.evidence");
    draft = removeNode(draft, "rerank");
    draft = addEdge(draft, { source: { node: "dense", port: "evidence" }, target: { node: "threshold", port: "evidence" } });
    const doc = toDocument(draft);
    expect(doc.nodes.map((n) => n.id)).toEqual(["prepare_query", "dense", "threshold"]);
    expect((doc.edges ?? []).map(edgeKey)).toEqual([
      "prepare_query.query->dense.query",
      "dense.evidence->threshold.evidence",
    ]);
  });

  it("removes a node's edges, graph inputs, outputs, position and selection", () => {
    let draft = chain();
    draft = toggleGraphInput(draft, "dense", "query", "query", true);
    draft = toggleGraphOutput(draft, "rerank", "evidence", true);
    draft = setSelection(draft, ["rerank", "dense"]);
    draft = removeNode(draft, "dense");
    const doc = toDocument(draft);
    expect((doc.edges ?? []).map(edgeKey)).toEqual(["rerank.evidence->threshold.evidence"]);
    expect(doc.inputs ?? []).toEqual([]);
    expect(doc.outputs).toEqual([{ name: "evidence", source: { node: "rerank", port: "evidence" } }]);
    expect(draft.layout.positions.dense).toBeUndefined();
    expect(draft.layout.selection).toEqual(["rerank"]);
  });

  it("shares one graph input between ports of the same kind and name", () => {
    let draft = chain();
    draft = toggleGraphInput(draft, "prepare_query", "query", "query", true);
    draft = toggleGraphInput(draft, "dense", "query", "query", true);
    expect(toDocument(draft).inputs).toEqual([
      {
        name: "query",
        kind: "query",
        targets: [
          { node: "prepare_query", port: "query" },
          { node: "dense", port: "query" },
        ],
      },
    ]);
    draft = toggleGraphInput(draft, "prepare_query", "query", "query", false);
    draft = toggleGraphInput(draft, "dense", "query", "query", false);
    expect(toDocument(draft).inputs).toBeUndefined();
  });

  it("drops inherited parameters and default enablement from the document", () => {
    let draft = chain();
    draft = setParam(draft, "rerank", "enabled", false);
    draft = setParam(draft, "prepare_query", "top_k", 8);
    draft = setEnabled(draft, "rerank", false);
    let doc = toDocument(draft);
    expect(doc.nodes.find((n) => n.id === "rerank")).toEqual({
      id: "rerank",
      operation: "select.rerank",
      version: 1,
      params: { enabled: false },
      enabled: false,
    });
    draft = setParam(draft, "rerank", "enabled", null);
    draft = setEnabled(draft, "rerank", true);
    doc = toDocument(draft);
    expect(doc.nodes.find((n) => n.id === "rerank")).toEqual({ id: "rerank", operation: "select.rerank", version: 1 });
    expect(doc.nodes.find((n) => n.id === "prepare_query")?.params).toEqual({ top_k: 8 });
  });

  it("treats a server revision with filled defaults as the same document", () => {
    const draft = chain();
    const server = {
      ...toDocument(draft),
      nodes: toDocument(draft).nodes.map((n) => ({ ...n, params: {}, enabled: true })),
      inputs: [],
      outputs: [],
      profile: null,
      collection: null,
      overrides: {},
    };
    expect(sameDocument(fromDocument(server, {}).graph, draft.graph)).toBe(true);
    expect(sameDocument(setParam(draft, "rerank", "enabled", true).graph, draft.graph)).toBe(false);
  });
});

describe("layout direction", () => {
  it("keeps the direction through fromDocument and toLayout", () => {
    const draft = fromDocument(null, { direction: "vertical" });
    expect(draft.layout.direction).toBe("vertical");
    expect(toLayout(draft).direction).toBe("vertical");
  });

  it("reads a stored layout without a direction as horizontal", () => {
    const draft = fromDocument(null, { positions: {} });
    expect(draft.layout.direction).toBe("horizontal");
    expect(toLayout(draft).direction).toBe("horizontal");
  });
});
