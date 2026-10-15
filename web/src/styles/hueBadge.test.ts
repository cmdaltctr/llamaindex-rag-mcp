import { describe, expect, it } from "vitest";
import { buildUtilities } from "./tailwind.testing";

describe("hue badge classes", () => {
  it("compile to oklch colours that read the per-badge hue variable", async () => {
    const css = await buildUtilities([
      "text-[oklch(0.42_0.13_var(--badge-hue))]",
      "dark:text-[oklch(0.8_0.13_var(--badge-hue))]",
      "border-current",
    ]);
    expect(css).toContain("oklch(0.42 0.13 var(--badge-hue))");
    expect(css).toContain("oklch(0.8 0.13 var(--badge-hue))");
    expect(css).toMatch(/border-color:\s*currentcolor/i);
  });
});
