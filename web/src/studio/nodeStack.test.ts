import { describe, expect, it } from "vitest";
import appCss from "../styles/app.css?raw";

describe("an expanded step card stacks above its neighbours", () => {
  it("lifts a node whose summary or settings are expanded, because the card can grow past its grid row", () => {
    const rule = /\.react-flow__node:has\(\[aria-expanded=["']true["']\]\)\s*\{[^}]*z-index:\s*\d+\s*!important/;
    expect(appCss).toMatch(rule);
  });
});
