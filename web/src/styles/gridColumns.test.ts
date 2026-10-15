import { describe, expect, it } from "vitest";

/**
 * A CSS grid with no base column definition gets one content-sized column.
 * A long unbreakable value (a path, a URL, an identifier) then stretches the
 * column past the viewport and the page scrolls sideways on a phone. Every
 * `grid` therefore names its columns for the smallest screen, for example
 * `grid-cols-1`, and adds breakpoint columns on top.
 */
const sources = import.meta.glob<string>("../**/*.tsx", { query: "?raw", import: "default", eager: true });

function classNames(source: string): string[] {
  return [...source.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\})/g)].map((match) => match[1] ?? match[2] ?? "");
}

describe("grid columns", () => {
  it("gives every grid a base column definition", () => {
    const offenders: string[] = [];
    for (const [path, source] of Object.entries(sources)) {
      if (/\.test\.tsx$/.test(path) || path.includes("/test/")) continue;
      for (const value of classNames(source)) {
        const tokens = value.split(/\s+/);
        if (tokens.includes("grid") && !tokens.some((token) => token.startsWith("grid-cols-"))) offenders.push(`${path}: ${value.slice(0, 90)}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
