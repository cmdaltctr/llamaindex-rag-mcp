import { afterEach, describe, expect, it, vi } from "vitest";
import { addNode, emptyDraft } from "./graph";
import { clearDraft, DRAFT_PREFIX, readDraft, writeDraft } from "./storage";
import { CATALOGUE } from "./test/catalogueFixture";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("draft storage", () => {
  it("keeps one draft per pipeline under omrg-canvas-draft:<pipeline-id>", () => {
    const one = addNode(emptyDraft("One"), CATALOGUE[0]!).draft;
    writeDraft("p1", one);
    writeDraft("p2", emptyDraft("Two"));
    expect(DRAFT_PREFIX).toBe("omrg-canvas-draft:");
    expect(window.localStorage.getItem("omrg-canvas-draft:p1")).not.toBeNull();
    expect(readDraft("p1")).toEqual(one);
    expect(readDraft("p2")?.layout.title).toBe("Two");
    expect(readDraft("p3")).toBeNull();
  });

  it("stores no version field", () => {
    writeDraft("p1", emptyDraft());
    expect(JSON.parse(window.localStorage.getItem("omrg-canvas-draft:p1") ?? "{}")).not.toHaveProperty("version");
  });

  it("ignores and removes corrupt or foreign data", () => {
    window.localStorage.setItem("omrg-canvas-draft:p1", "{not json");
    expect(readDraft("p1")).toBeNull();
    window.localStorage.setItem("omrg-canvas-draft:p1", JSON.stringify({ graph: { nodes: "x" } }));
    expect(readDraft("p1")).toBeNull();
    expect(window.localStorage.getItem("omrg-canvas-draft:p1")).toBeNull();
  });

  it("clears one draft", () => {
    writeDraft("p1", emptyDraft());
    clearDraft("p1");
    expect(readDraft("p1")).toBeNull();
  });

  it("survives storage that throws", () => {
    for (const method of ["getItem", "setItem", "removeItem"] as const) {
      vi.spyOn(Storage.prototype, method).mockImplementation(() => {
        throw new Error("blocked");
      });
    }
    expect(() => writeDraft("p1", emptyDraft())).not.toThrow();
    expect(() => clearDraft("p1")).not.toThrow();
    expect(readDraft("p1")).toBeNull();
  });

  it("keeps the draft for the rest of the session when storage throws", () => {
    for (const method of ["getItem", "setItem", "removeItem"] as const) {
      vi.spyOn(Storage.prototype, method).mockImplementation(() => {
        throw new Error("blocked");
      });
    }
    const draft = emptyDraft("Kept");
    writeDraft("p1", draft);
    expect(readDraft("p1")).toEqual(draft);
    clearDraft("p1");
    expect(readDraft("p1")).toBeNull();
  });

  it("forgets the session copy of a draft when the stored one is cleared", () => {
    writeDraft("p1", emptyDraft("One"));
    clearDraft("p1");
    expect(readDraft("p1")).toBeNull();
  });

  it("no longer keeps a canvas session key", () => {
    writeDraft("p1", emptyDraft());
    expect(window.localStorage.getItem("omrg-canvas-session")).toBeNull();
  });
});
