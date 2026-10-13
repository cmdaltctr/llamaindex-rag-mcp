import { describe, expect, it } from "vitest";
import { checkConnection, connectionGuard, portCompatibility } from "./connections";
import { addEdge, addNode, emptyDraft, type Draft } from "./graph";
import { CATALOGUE } from "./test/catalogueFixture";

function op(id: string) {
  const found = CATALOGUE.find((entry) => entry.operation_id === id);
  if (found === undefined) throw new Error(id);
  return found;
}

function draftWith(...ids: string[]): Draft {
  return ids.reduce((draft, id) => addNode(draft, op(id)).draft, emptyDraft());
}

const ref = (node: string, port: string) => ({ node, port });

describe("connection checks", () => {
  it("accepts compatible ports", () => {
    const draft = draftWith("retrieve.prepare_query", "retrieve.dense");
    expect(checkConnection(draft, CATALOGUE, ref("prepare_query", "query"), ref("dense", "query"))).toBeNull();
  });

  it("refuses a different value kind and names both ports", () => {
    const draft = draftWith("retrieve.prepare_query", "select.threshold");
    const reason = checkConnection(draft, CATALOGUE, ref("prepare_query", "query"), ref("threshold", "evidence"));
    expect(reason).toMatch(/query/);
    expect(reason).toMatch(/ranked_evidence/);
  });

  it("refuses a rank-only score kind into a scored-evidence port", () => {
    const draft = draftWith("retrieve.sparse", "select.threshold");
    const reason = checkConnection(draft, CATALOGUE, ref("sparse", "evidence"), ref("threshold", "evidence"));
    expect(reason).toMatch(/sparse_rank_v1/);
  });

  it("refuses missing provenance, embedding identity and reader declarations", () => {
    const base = { kind: "chunks", provenance: [], score_kinds: null, embedding_identity: false, reader_declarations: [] };
    expect(portCompatibility(base, { ...base, provenance: ["source"] })).toEqual([
      "the value does not carry the required provenance: source",
    ]);
    expect(portCompatibility(base, { ...base, embedding_identity: true })).toEqual([
      "the input needs values bound to the host embedding model",
    ]);
    expect(portCompatibility(base, { ...base, reader_declarations: ["text_format"] })).toEqual([
      "reader declarations are not preserved: text_format",
    ]);
    expect(portCompatibility({ ...base, kind: "ranked_evidence" }, { ...base, kind: "ranked_evidence", score_kinds: ["rrf_v1"] })).toEqual([
      "the output declares no score kind; the input accepts only rrf_v1",
    ]);
  });

  it("refuses a second connection into a single-value port", () => {
    let draft = draftWith("retrieve.dense", "retrieve.dense", "select.threshold");
    draft = addEdge(draft, { source: ref("dense", "evidence"), target: ref("threshold", "evidence") });
    const reason = checkConnection(draft, CATALOGUE, ref("dense_2", "evidence"), ref("threshold", "evidence"));
    expect(reason).toMatch(/accepts one connection/);
  });

  it("accepts several connections into a many port", () => {
    let draft = draftWith("retrieve.dense", "retrieve.dense", "combine.rrf");
    draft = addEdge(draft, { source: ref("dense", "evidence"), target: ref("rrf", "ranked") });
    expect(checkConnection(draft, CATALOGUE, ref("dense_2", "evidence"), ref("rrf", "ranked"))).toBeNull();
  });

  it("refuses a connection that closes a loop", () => {
    let draft = draftWith("combine.rrf", "select.rerank");
    draft = addEdge(draft, { source: ref("rrf", "evidence"), target: ref("rerank", "evidence") });
    const reason = checkConnection(draft, CATALOGUE, ref("rerank", "evidence"), ref("rrf", "ranked"));
    expect(reason).toMatch(/loop/);
  });

  it("refuses a self connection and a duplicate connection", () => {
    let draft = draftWith("select.rerank", "select.threshold");
    expect(checkConnection(draft, CATALOGUE, ref("rerank", "evidence"), ref("rerank", "evidence"))).toMatch(/itself/);
    draft = addEdge(draft, { source: ref("rerank", "evidence"), target: ref("threshold", "evidence") });
    expect(checkConnection(draft, CATALOGUE, ref("rerank", "evidence"), ref("threshold", "evidence"))).toMatch(
      /already connected/,
    );
  });

  it("refuses unknown ports", () => {
    const draft = draftWith("retrieve.dense", "select.threshold");
    expect(checkConnection(draft, CATALOGUE, ref("dense", "nope"), ref("threshold", "evidence"))).toMatch(/no output/);
  });

  it("guards drag connections from the flow surface", () => {
    const draft = draftWith("retrieve.sparse", "select.threshold", "combine.rrf");
    const guard = connectionGuard(draft, CATALOGUE);
    expect(guard({ source: "sparse", sourceHandle: "evidence", target: "threshold", targetHandle: "evidence" })).toBe(false);
    expect(guard({ source: "sparse", sourceHandle: "evidence", target: "rrf", targetHandle: "ranked" })).toBe(true);
    expect(guard({ source: "sparse", sourceHandle: null, target: "rrf", targetHandle: "ranked" })).toBe(false);
  });
});
