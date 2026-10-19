import { describe, expect, it } from "vitest";
import { SECTIONS } from "./panelSections";

describe("panel sections", () => {
  it("lists the six sections in order, with Pipeline settings before Operations", () => {
    expect(SECTIONS.map((section) => section.title)).toEqual([
      "Pipeline settings",
      "Operations",
      "Steps and connections",
      "Connect ports",
      "Revision and run",
      "Step settings",
    ]);
  });

  it("uses no section title that contains the word node", () => {
    for (const section of SECTIONS) expect(section.title.toLowerCase()).not.toContain("node");
  });

  it("keeps the section ids", () => {
    expect(SECTIONS.map((section) => section.id)).toEqual(["pipeline-settings", "operations", "nodes", "connect", "run", "node-settings"]);
  });

  it("gives every section its own icon", () => {
    expect(new Set(SECTIONS.map((section) => section.icon)).size).toBe(SECTIONS.length);
  });

  it("gives every section a unique id", () => {
    expect(new Set(SECTIONS.map((section) => section.id)).size).toBe(SECTIONS.length);
  });
});
