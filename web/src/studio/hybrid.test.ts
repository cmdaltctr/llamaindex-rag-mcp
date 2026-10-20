import { describe, expect, it } from "vitest";
import type { EdgeSpec, GraphDocument, OperationDescriptor } from "../api/pipelines";
import { edgeKey, fromDocument, toDocument, type Draft } from "./graph";
import { disableHybrid, enableHybrid, hybridState } from "./hybrid";
import { CATALOGUE } from "./test/catalogueFixture";

const edge = (from: string, out: string, to: string, into: string): EdgeSpec => ({ source: { node: from, port: out }, target: { node: to, port: into } });

/** The plain Search template (`_search_graph(None, hybrid=False, rerank=True)`). */
const SEARCH: GraphDocument = {
  schema_version: 1,
  nodes: [
    { id: "prepare", operation: "retrieve.prepare_query", version: 1 },
    { id: "dense", operation: "retrieve.dense", version: 1 },
    { id: "rerank", operation: "select.rerank", version: 1, enabled: true },
    { id: "select", operation: "select.threshold", version: 1 },
    { id: "context", operation: "context.assemble", version: 1 },
  ],
  edges: [
    edge("prepare", "query", "dense", "query"),
    edge("dense", "evidence", "rerank", "evidence"),
    edge("rerank", "evidence", "select", "evidence"),
    edge("select", "evidence", "context", "evidence"),
  ],
  inputs: [{ name: "query", kind: "query", targets: [{ node: "prepare", port: "query" }] }],
  outputs: [{ name: "results", source: { node: "context", port: "context" } }],
  profile: "documents",
};

/** The plain Answer template: the Search chain plus the answer steps. */
const ANSWER: GraphDocument = {
  ...SEARCH,
  nodes: [
    ...SEARCH.nodes,
    { id: "evidence", operation: "answer.prepare_evidence", version: 1 },
    { id: "synthesise", operation: "answer.synthesise", version: 1 },
  ],
  edges: [...SEARCH.edges!, edge("context", "context", "evidence", "context"), edge("evidence", "context", "synthesise", "context")],
  inputs: [{ name: "query", kind: "query", targets: [{ node: "prepare", port: "query" }, { node: "synthesise", port: "query" }] }],
  outputs: [{ name: "answer", source: { node: "synthesise", port: "answer" } }],
};

const POSITIONS = { prepare: { x: 0, y: 0 }, dense: { x: 260, y: 0 }, rerank: { x: 520, y: 0 }, select: { x: 780, y: 0 }, context: { x: 1040, y: 0 } };

function draftOf(document: GraphDocument): Draft {
  return fromDocument(document, { positions: POSITIONS });
}

const keys = (draft: Draft) => draft.graph.edges.map(edgeKey).sort();
const ops = (draft: Draft) => Object.fromEntries(draft.graph.nodes.map((node) => [node.id, node.operation]));

function unavailable(operationId: string, reason: string): OperationDescriptor[] {
  return CATALOGUE.map((entry) => (entry.operation_id === operationId ? { ...entry, available: false, unavailable_reasons: [reason] } : entry));
}

describe("hybridState", () => {
  it("reads off on the plain Search and Answer graphs", () => {
    expect(hybridState(draftOf(SEARCH), CATALOGUE)).toEqual({ kind: "off" });
    expect(hybridState(draftOf(ANSWER), CATALOGUE)).toEqual({ kind: "off" });
  });

  it("reads on after the switch turns hybrid on", () => {
    expect(hybridState(enableHybrid(draftOf(SEARCH)), CATALOGUE)).toEqual({ kind: "on" });
    expect(hybridState(enableHybrid(draftOf(ANSWER)), CATALOGUE)).toEqual({ kind: "on" });
  });

  it("reads custom for two Dense retrieval steps", () => {
    const document = { ...SEARCH, nodes: [...SEARCH.nodes, { id: "dense_2", operation: "retrieve.dense", version: 1 }] };
    expect(hybridState(draftOf(document), CATALOGUE)).toEqual({ kind: "custom", on: false });
  });

  it("reads custom for a fusion step without Sparse retrieval", () => {
    const document = { ...SEARCH, nodes: [...SEARCH.nodes, { id: "fuse", operation: "combine.rrf", version: 1 }] };
    expect(hybridState(draftOf(document), CATALOGUE)).toEqual({ kind: "custom", on: false });
  });

  it("reads custom when Prepare query does not feed Dense retrieval", () => {
    const document = { ...SEARCH, edges: SEARCH.edges!.slice(1) };
    expect(hybridState(draftOf(document), CATALOGUE)).toEqual({ kind: "custom", on: false });
  });

  it("reads custom, still on, for a hybrid graph whose fusion step has a third input", () => {
    const on = enableHybrid(draftOf(SEARCH));
    const extra = { ...on, graph: { ...on.graph, edges: [...on.graph.edges, edge("prepare", "query", "fuse", "ranked")] } };
    expect(hybridState(extra, CATALOGUE)).toEqual({ kind: "custom", on: true });
  });

  it("reads unavailable with the catalogue reason", () => {
    const catalogue = unavailable("retrieve.sparse", "The sparse backend is not installed.");
    expect(hybridState(draftOf(SEARCH), catalogue)).toEqual({ kind: "unavailable", on: false, reason: "The sparse backend is not installed." });
  });
});

describe("enableHybrid", () => {
  it("adds Sparse retrieval and fusion with the canonical connections", () => {
    const on = enableHybrid(draftOf(SEARCH));
    expect(ops(on)).toMatchObject({ sparse: "retrieve.sparse", fuse: "combine.rrf" });
    expect(keys(on)).toEqual(
      [
        "prepare.query->dense.query",
        "prepare.query->sparse.query",
        "dense.evidence->fuse.ranked",
        "sparse.evidence->fuse.ranked",
        "fuse.evidence->rerank.evidence",
        "rerank.evidence->select.evidence",
        "select.evidence->context.evidence",
      ].sort(),
    );
    expect(keys(on)).not.toContain("dense.evidence->rerank.evidence");
  });

  it("keeps step settings and copies the Dense retrieval collection to Sparse retrieval", () => {
    const document = {
      ...SEARCH,
      nodes: SEARCH.nodes.map((node) =>
        node.id === "prepare" ? { ...node, params: { top_k: 20 } } : node.id === "dense" ? { ...node, params: { collection: "papers" } } : node,
      ),
    };
    const on = toDocument(enableHybrid(draftOf(document)));
    expect(on.nodes.find((node) => node.id === "prepare")?.params).toEqual({ top_k: 20 });
    expect(on.nodes.find((node) => node.id === "dense")?.params).toEqual({ collection: "papers" });
    expect(on.nodes.find((node) => node.id === "sparse")?.params).toEqual({ collection: "papers" });
  });

  it("keeps the position of every existing step and places the new steps", () => {
    const on = enableHybrid(draftOf(SEARCH));
    for (const [id, at] of Object.entries(POSITIONS)) expect(on.layout.positions[id]).toEqual(at);
    expect(on.layout.positions.sparse).toBeDefined();
    expect(on.layout.positions.fuse).toBeDefined();
  });

  it("uses sparse_2 and fuse_2 when sparse and fuse are taken", () => {
    const document = {
      ...SEARCH,
      nodes: SEARCH.nodes.map((node) => (node.id === "rerank" ? { ...node, id: "sparse" } : node.id === "select" ? { ...node, id: "fuse" } : node)),
      edges: [edge("prepare", "query", "dense", "query"), edge("dense", "evidence", "sparse", "evidence"), edge("sparse", "evidence", "fuse", "evidence")],
    };
    const on = enableHybrid(draftOf(document));
    expect(ops(on)).toMatchObject({ sparse: "select.rerank", fuse: "select.threshold", sparse_2: "retrieve.sparse", fuse_2: "combine.rrf" });
    expect(keys(on)).toContain("fuse_2.evidence->sparse.evidence");
  });
});

describe("disableHybrid", () => {
  it.each([
    ["Search", SEARCH],
    ["Answer", ANSWER],
  ])("gives the %s graph back after on then off", (_, document) => {
    const before = draftOf(document);
    const after = disableHybrid(enableHybrid(before));
    expect(toDocument(after)).toEqual(toDocument(before));
    expect(after.layout.positions).toEqual(before.layout.positions);
  });

  it("reconnects Dense retrieval to the step that fusion fed", () => {
    const off = disableHybrid(enableHybrid(draftOf(SEARCH)));
    expect(keys(off)).toContain("dense.evidence->rerank.evidence");
    expect(Object.keys(ops(off))).not.toContain("sparse");
    expect(Object.keys(ops(off))).not.toContain("fuse");
  });
});
