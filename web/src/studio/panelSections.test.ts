import { describe, expect, it } from "vitest";
import { SECTIONS } from "./panelSections";

describe("panel sections", () => {
  it("lists the six sections in order, with Pipeline settings before Operations", () => {
    expect(SECTIONS.map((section) => section.title)).toEqual([
      "Pipeline settings",
      "Operations",
      "Nodes and connections",
      "Connect ports",
      "Revision and run",
      "Node settings",
    ]);
  });

  it("gives every section its own icon", () => {
    expect(new Set(SECTIONS.map((section) => section.icon)).size).toBe(SECTIONS.length);
  });

  it("gives every section a unique id", () => {
    expect(new Set(SECTIONS.map((section) => section.id)).size).toBe(SECTIONS.length);
  });
});
