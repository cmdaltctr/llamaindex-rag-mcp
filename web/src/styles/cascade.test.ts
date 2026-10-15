/**
 * Guards for the stylesheet architecture (web-ui-stack): only tokens.css and
 * app.css exist, app.css loads Tailwind and third-party CSS into fixed cascade
 * layers, and only main.tsx imports CSS. See the header of app.css.
 */
import { describe, expect, it } from "vitest";
import appCss from "./app.css?raw";
import mainSource from "../main.tsx?raw";
import { buildUtilities } from "./tailwind.testing";

const sources = import.meta.glob<string>("../**/*.{tsx,ts,css}", {
  query: "?raw",
  import: "default",
  eager: true,
});

const isTest = (path: string) => /\.test\.tsx?$/.test(path);

describe("stylesheet layering", () => {
  it("declares the layer order, with utilities last", () => {
    const order = /@layer\s+([\w\s,-]+);/.exec(appCss)?.[1]?.split(",").map((l) => l.trim());
    expect(order).toEqual(["theme", "base", "vendor", "components", "utilities"]);
  });

  it("loads Tailwind theme, preflight and utilities into their layers", () => {
    expect(appCss).toMatch(/@import "tailwindcss\/theme\.css" layer\(theme\);/);
    expect(appCss).toMatch(/@import "tailwindcss\/preflight\.css" layer\(base\);/);
    expect(appCss).toMatch(/@import "tailwindcss\/utilities\.css" layer\(utilities\);/);
  });

  it("imports every third-party stylesheet into the vendor layer", () => {
    const imports = [...appCss.matchAll(/^@import\s+"([^"]+)"([^;]*);/gm)];
    const thirdParty = imports.filter(([, id]) => !(id as string).startsWith("tailwindcss/") && id !== "tw-animate-css");
    expect(thirdParty.length).toBeGreaterThan(0);
    for (const [, id, rest] of thirdParty) {
      expect(rest, `${id} must be imported with layer(vendor)`).toMatch(/layer\(vendor\)/);
    }
  });

  it("has no legacy layer", () => {
    expect(appCss).not.toMatch(/\blegacy\b/);
  });

  it("generates the preflight reset in the base layer", async () => {
    const css = await buildUtilities(["flex"]);
    const base = /@layer base\s*\{([\s\S]*?)\n\}\n/.exec(css)?.[1] ?? "";
    expect(base).toContain("box-sizing: border-box");
    expect(base).toMatch(/button/);
  });

  it("keeps the layer order in the generated CSS, so a utility beats a higher-specificity vendor rule", async () => {
    const css = await buildUtilities(["flex"]);
    expect(css).toContain("@layer theme, base, vendor, components, utilities;");
  });
});

describe("stylesheet files", () => {
  const css = Object.keys(sources).filter((path) => path.endsWith(".css"));

  it("has only tokens.css and app.css", () => {
    expect(css.sort()).toEqual(["./app.css", "./tokens.css"]);
  });

  it("lets only main.tsx import CSS, so no stylesheet bypasses its layer", () => {
    for (const [path, source] of Object.entries(sources)) {
      if (isTest(path) || path === "../main.tsx" || !path.endsWith(".tsx")) continue;
      expect(source, `${path} imports a stylesheet`).not.toMatch(/^import\s+(?:[^;]*from\s+)?"[^"]+\.css(\?[^"]*)?";/m);
    }
    expect(mainSource).toMatch(/import "\.\/styles\/tokens\.css";\s*import "\.\/styles\/app\.css";/);
  });
});

describe("global rules", () => {
  it("keeps the focus ring, hidden attribute and reduced-motion rules in the base layer", () => {
    expect(appCss).toMatch(/@layer base\s*\{[\s\S]*:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--focus-ring\)/);
    expect(appCss).toMatch(/\[hidden\]\s*\{\s*display:\s*none !important/);
    expect(appCss).toMatch(/prefers-reduced-motion:\s*reduce/);
    expect(appCss).toMatch(/body\s*\{[^}]*background:\s*var\(--surface-canvas\)/);
  });
});
