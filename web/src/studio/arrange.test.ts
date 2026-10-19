import { describe, expect, it } from "vitest";
import { arrangeLayout, type ArrangeInput } from "./arrange";

const SIZE = { width: 200, height: 80 };

function input(ids: string[], edges: [string, string][], direction: ArrangeInput["direction"] = "horizontal", sizes: ArrangeInput["sizes"] = {}): ArrangeInput {
  return { nodeIds: ids, edges: edges.map(([source, target]) => ({ source, target })), direction, sizes };
}

describe("arrangeLayout layers", () => {
  it("puts a chain on increasing x with one y when horizontal", () => {
    const p = arrangeLayout(input(["a", "b", "c"], [["a", "b"], ["b", "c"]]));
    expect(p.a!.x).toBeLessThan(p.b!.x);
    expect(p.b!.x).toBeLessThan(p.c!.x);
    expect(new Set([p.a!.y, p.b!.y, p.c!.y]).size).toBe(1);
  });

  it("uses the longest path, so a shortcut edge does not pull a node back", () => {
    const p = arrangeLayout(input(["a", "b", "c"], [["a", "b"], ["b", "c"], ["a", "c"]]));
    expect(p.c!.x).toBeGreaterThan(p.b!.x);
  });

  it("puts the two branches of a diamond in one layer and the join after them", () => {
    const p = arrangeLayout(input(["a", "b", "c", "d"], [["a", "b"], ["a", "c"], ["b", "d"], ["c", "d"]]));
    expect(p.b!.x).toBe(p.c!.x);
    expect(p.b!.y).not.toBe(p.c!.y);
    expect(p.d!.x).toBeGreaterThan(p.b!.x);
  });

  it("puts a node with no edges in the first layer", () => {
    const p = arrangeLayout(input(["a", "b", "lone"], [["a", "b"]]));
    expect(p.lone!.x).toBe(p.a!.x);
  });

  it("ignores edges that name a node that is not there", () => {
    const p = arrangeLayout(input(["a", "b"], [["a", "ghost"], ["a", "b"]]));
    expect(p.b!.x).toBeGreaterThan(p.a!.x);
  });
});

describe("arrangeLayout direction", () => {
  it("puts a chain on increasing y with one x when vertical", () => {
    const p = arrangeLayout(input(["a", "b", "c"], [["a", "b"], ["b", "c"]], "vertical"));
    expect(p.a!.y).toBeLessThan(p.b!.y);
    expect(p.b!.y).toBeLessThan(p.c!.y);
    expect(new Set([p.a!.x, p.b!.x, p.c!.x]).size).toBe(1);
  });

  it("spreads the branches of a diamond across x when vertical", () => {
    const p = arrangeLayout(input(["a", "b", "c", "d"], [["a", "b"], ["a", "c"], ["b", "d"], ["c", "d"]], "vertical"));
    expect(p.b!.y).toBe(p.c!.y);
    expect(p.b!.x).not.toBe(p.c!.x);
  });
});

describe("arrangeLayout sizes and fallbacks", () => {
  it("leaves room for the measured width of a node", () => {
    const wide = arrangeLayout(input(["a", "b"], [["a", "b"]], "horizontal", { a: { width: 500, height: 80 } }));
    const narrow = arrangeLayout(input(["a", "b"], [["a", "b"]], "horizontal", { a: SIZE }));
    expect(wide.b!.x - wide.a!.x).toBeGreaterThan(narrow.b!.x - narrow.a!.x);
    expect(wide.b!.x - wide.a!.x).toBeGreaterThanOrEqual(500);
  });

  it("does not overlap two nodes of one layer", () => {
    const p = arrangeLayout(input(["a", "b", "c"], [["a", "b"], ["a", "c"]], "horizontal", { b: { width: 200, height: 300 } }));
    expect(Math.abs(p.c!.y - p.b!.y)).toBeGreaterThanOrEqual(300);
  });

  it("falls back to the first layer in input order when the graph has a cycle", () => {
    const p = arrangeLayout(input(["a", "b", "c"], [["a", "b"], ["b", "a"], ["b", "c"]]));
    expect(new Set([p.a!.x, p.b!.x, p.c!.x]).size).toBe(1);
    expect(p.a!.y).toBeLessThan(p.b!.y);
    expect(p.b!.y).toBeLessThan(p.c!.y);
  });

  it("gives the same answer for the same input", () => {
    const i = input(["a", "b", "c"], [["a", "b"], ["a", "c"]]);
    expect(arrangeLayout(i)).toEqual(arrangeLayout(i));
  });

  it("returns nothing for no nodes", () => {
    expect(arrangeLayout(input([], []))).toEqual({});
  });
});
