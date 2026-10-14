/**
 * The token bridge in app.css gives Tailwind class names to the custom
 * properties in tokens.css. jsdom applies no stylesheets, so these tests check
 * the CSS that Tailwind generates, plus that every alias points at a token that
 * exists. A utility with no matching theme key produces no CSS and no error,
 * so a typo in the bridge would otherwise pass unnoticed.
 */
import { describe, expect, it } from "vitest";
import appCss from "./app.css?raw";
import tokensCss from "./tokens.css?raw";
import { buildUtilities } from "./tailwind.testing";

const STATUSES = ["error", "warning", "success", "info"] as const;

/** The declarations Tailwind generated for one rule, with spacing normalised. */
function declarations(css: string, escapedSelector: string): string {
  const start = css.indexOf(`${escapedSelector} {`);
  if (start < 0) return "";
  return css.slice(start, css.indexOf("}", start)).replace(/\s+/g, " ");
}

/** The body of the `@theme inline { ... }` block. */
function bridgeBlock(): string {
  const start = appCss.indexOf("@theme inline {");
  expect(start, "app.css has an @theme inline block").toBeGreaterThan(-1);
  return appCss.slice(start, appCss.indexOf("\n}", start));
}

describe("token bridge", () => {
  it("maps utility classes to the tokens.css custom properties", async () => {
    const css = await buildUtilities([
      "bg-background",
      "bg-card",
      "text-foreground",
      "text-muted-foreground",
      "border-border",
      "text-primary-label",
      "bg-primary-tint",
      "bg-selection",
      "rounded-control",
      "rounded-panel",
      "text-meta",
      "text-ui",
      "font-mono",
      ...STATUSES.map((s) => `text-status-${s}-label`),
    ]);
    const expected: Array<[string, string]> = [
      ["bg-background", "background-color: var(--surface-canvas)"],
      ["bg-card", "background-color: var(--surface-elevated)"],
      ["text-foreground", "color: var(--text-primary)"],
      ["text-muted-foreground", "color: var(--text-secondary)"],
      ["border-border", "border-color: var(--border)"],
      ["text-primary-label", "color: var(--accent-label)"],
      ["bg-primary-tint", "background-color: var(--accent-tint)"],
      ["bg-selection", "background-color: var(--selection)"],
      ["rounded-control", "border-radius: var(--radius-control)"],
      ["rounded-panel", "border-radius: var(--radius-panel)"],
      ["text-meta", "font-size: var(--text-meta)"],
      ["text-ui", "font-size: var(--text-ui)"],
      ["font-mono", "font-family: var(--font-mono)"],
      ...STATUSES.map((s): [string, string] => [
        `text-status-${s}-label`,
        `color: var(--status-${s}-label)`,
      ]),
    ];
    for (const [name, declaration] of expected) {
      expect(declarations(css, `.${name}`), `.${name}`).toContain(declaration);
    }
  });

  it("generates the elevation shadow from the shadow token", async () => {
    const css = await buildUtilities(["shadow-floating"]);
    expect(declarations(css, ".shadow-floating")).toContain("var(--shadow-floating)");
  });

  it("applies status tints through the status tokens", async () => {
    const css = await buildUtilities(["bg-status-error/10"]);
    expect(declarations(css, ".bg-status-error\\/10")).toContain("var(--status-error)");
  });

  it("makes the dark: variant follow data-theme, then the system preference", async () => {
    const css = await buildUtilities(["dark:bg-destructive/16"]);
    expect(css).toContain('[data-theme="dark"]');
    expect(css).toContain("@media (prefers-color-scheme: dark)");
    expect(css).toContain(':not([data-theme="light"])');
  });

  it("points every alias at a custom property that tokens.css declares", () => {
    const referenced = [...bridgeBlock().matchAll(/var\((--[\w-]+)\)/g)].map((m) => m[1] as string);
    expect(referenced.length).toBeGreaterThan(30);
    const declared = new Set([...tokensCss.matchAll(/^\s*(--[\w-]+):/gm)].map((m) => m[1]));
    const missing = [...new Set(referenced)].filter((name) => !declared.has(name));
    expect(missing, "bridge aliases with no token").toEqual([]);
  });

  it("holds no literal colours, so tokens.css stays the only source", () => {
    expect(bridgeBlock()).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|oklch\(/);
  });
});
