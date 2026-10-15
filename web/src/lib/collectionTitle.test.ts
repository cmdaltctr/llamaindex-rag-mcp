import { describe, expect, it } from "vitest";
import { collectionTitle, DISPLAY_NAME_MAX, displayNameProblem } from "./collectionTitle";

const base = { name: "documents", document_count: 1, chunk_count: 2, profile: null, store: { name: "lancedb", label: "LanceDB" } };

describe("collectionTitle", () => {
  it("shows the display name when one is set", () => {
    expect(collectionTitle({ ...base, display_name: "Project docs" })).toBe("Project docs");
  });

  it("falls back to the collection name when none is set", () => {
    expect(collectionTitle({ ...base, display_name: null })).toBe("documents");
  });
});

describe("displayNameProblem", () => {
  it("accepts a normal name, an empty value (clear) and exactly the limit", () => {
    expect(displayNameProblem("Project docs")).toBeNull();
    expect(displayNameProblem("   ")).toBeNull();
    expect(displayNameProblem("a".repeat(DISPLAY_NAME_MAX))).toBeNull();
  });

  it("counts Unicode code points, not UTF-16 units, like the server", () => {
    const emoji = "\u{1F600}";
    expect(displayNameProblem(emoji.repeat(DISPLAY_NAME_MAX))).toBeNull();
    expect(displayNameProblem(emoji.repeat(DISPLAY_NAME_MAX + 1))).toMatch(/at most 80/);
  });

  it("measures the trimmed value", () => {
    expect(displayNameProblem(`  ${"a".repeat(DISPLAY_NAME_MAX)}  `)).toBeNull();
  });

  it("refuses a control character", () => {
    for (const bad of ["a\nb", "a\tb", "a\u0000b", "a\u007Fb"]) expect(displayNameProblem(bad)).toMatch(/control/i);
  });
});
