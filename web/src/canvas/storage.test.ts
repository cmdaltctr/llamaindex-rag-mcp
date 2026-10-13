import { afterEach, describe, expect, it, vi } from "vitest";
import { addNode, emptyDraft } from "./graph";
import { readDraft, readSession, writeDraft, writeSession } from "./storage";
import { CATALOGUE } from "./test/catalogueFixture";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("draft storage", () => {
  it("keeps one draft per pipeline", () => {
    const one = addNode(emptyDraft("One"), CATALOGUE[0]!).draft;
    writeDraft("p1", one);
    writeDraft("p2", emptyDraft("Two"));
    expect(readDraft("p1")).toEqual(one);
    expect(readDraft("p2")?.layout.title).toBe("Two");
    expect(readDraft("p3")).toBeNull();
  });

  it("ignores corrupt or foreign data", () => {
    window.localStorage.setItem("omrg-canvas-draft:p1", "{not json");
    expect(readDraft("p1")).toBeNull();
    window.localStorage.setItem("omrg-canvas-draft:p1", JSON.stringify({ version: 1, graph: { nodes: "x" } }));
    expect(readDraft("p1")).toBeNull();
    window.localStorage.setItem("omrg-canvas-draft:p1", JSON.stringify({ version: 9 }));
    expect(readDraft("p1")).toBeNull();
  });

  it("survives storage that throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => writeDraft("p1", emptyDraft())).not.toThrow();
    expect(readDraft("p1")).toBeNull();
    expect(() => writeSession({ pipelineId: "p1", run: null })).not.toThrow();
    expect(readSession()).toEqual({ pipelineId: null, run: null });
  });

  it("remembers the open pipeline and the submitted run", () => {
    const run = {
      runId: "run1",
      status: "queued",
      revisionId: "r1",
      revisionNumber: 2,
      document: { schema_version: 1, nodes: [{ id: "a", operation: "x.y" }] },
    };
    writeSession({ pipelineId: "p1", run });
    expect(readSession()).toEqual({ pipelineId: "p1", run });
  });
});
