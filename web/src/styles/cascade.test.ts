/**
 * Guards for the stylesheet architecture: legacy and vendor CSS sit in cascade
 * layers below Tailwind utilities, nothing imports CSS around app.css, and no
 * legacy class name collides with a Tailwind utility. See the header of
 * app.css for the rules these tests protect.
 */
import { describe, expect, it } from "vitest";
import appCss from "./app.css?raw";
import mainSource from "../main.tsx?raw";
import { buildUtilities, generatesClass } from "./tailwind.testing";

const sources = import.meta.glob<string>("../**/*.{tsx,css}", {
  query: "?raw",
  import: "default",
  eager: true,
});

const isTest = (path: string) => /\.test\.tsx?$/.test(path);
// Primitives are Tailwind utility code, so their class names are meant to be utilities.
const isPrimitive = (path: string) => path.startsWith("../components/ui/");

const markupFiles = Object.entries(sources).filter(
  ([path]) => path.endsWith(".tsx") && !isTest(path) && !isPrimitive(path),
);
const cssFiles = Object.entries(sources).filter(([path]) => path.endsWith(".css"));
const legacyCssFiles = cssFiles.filter(
  ([path]) => path !== "./tokens.css" && path !== "./app.css",
);

/** Every string literal inside the value of each className attribute. */
function classNameLiterals(source: string): string[] {
  const found: string[] = [];
  for (const match of source.matchAll(/className=/g)) {
    let i = (match.index ?? 0) + match[0].length;
    let chunk: string;
    if (source[i] === '"') {
      const end = source.indexOf('"', i + 1);
      chunk = source.slice(i, end + 1);
    } else if (source[i] === "{") {
      let depth = 0;
      const start = i;
      for (; i < source.length; i += 1) {
        if (source[i] === "{") depth += 1;
        if (source[i] === "}") depth -= 1;
        if (depth === 0) break;
      }
      chunk = source.slice(start, i + 1);
    } else continue;
    for (const literal of chunk.matchAll(/"([^"]*)"|'([^']*)'|`([^`]*)`/g)) {
      found.push((literal[1] ?? literal[2] ?? literal[3] ?? "").replace(/\$\{[^}]*\}/g, " "));
    }
  }
  return found;
}

/** Class names used in a selector list, ignoring declaration blocks and at-rules. */
function selectorClasses(css: string): string[] {
  const stripped = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const names: string[] = [];
  let buffer = "";
  for (const char of stripped) {
    if (char === "{") {
      if (!buffer.trim().startsWith("@")) {
        for (const m of buffer.matchAll(/\.([A-Za-z_][\w-]*)/g)) names.push(m[1] as string);
      }
      buffer = "";
    } else if (char === "}" || char === ";") buffer = "";
    else buffer += char;
  }
  return names;
}

describe("stylesheet layering", () => {
  it("declares the layer order, with utilities last and legacy below components", () => {
    const order = /@layer\s+([\w\s,-]+);/.exec(appCss)?.[1]?.split(",").map((l) => l.trim());
    expect(order).toEqual(["theme", "base", "vendor", "legacy", "components", "utilities"]);
  });

  it("imports every non-Tailwind stylesheet into a layer", () => {
    const imports = [...appCss.matchAll(/^@import\s+"([^"]+)"([^;]*);/gm)];
    const outsideTailwind = imports.filter(
      ([, id]) => !(id as string).startsWith("tailwindcss/") && id !== "tw-animate-css",
    );
    expect(outsideTailwind.length).toBeGreaterThan(0);
    for (const [, id, rest] of outsideTailwind) {
      expect(rest, `${id} must be imported with layer(...)`).toMatch(/layer\((vendor|legacy)\)/);
    }
  });

  it("imports every legacy stylesheet exactly once", () => {
    for (const [path] of legacyCssFiles) {
      const name = path.replace(/^\.\.\//, "../").replace(/^\.\//, "./");
      const count = appCss.split(`"${name}"`).length - 1;
      expect(count, `${name} should be imported once by app.css`).toBe(1);
    }
  });

  it("lets only main.tsx import CSS, so no stylesheet bypasses its layer", () => {
    for (const [path, source] of markupFiles.filter(([p]) => p !== "../main.tsx")) {
      expect(source, `${path} imports a stylesheet`).not.toMatch(/^import\s+"[^"]+\.css";/m);
    }
    expect(mainSource).toMatch(/import "\.\/styles\/tokens\.css";\s*import "\.\/styles\/app\.css";/);
  });
});

describe("legacy class names", () => {
  it("never collide with a Tailwind utility", async () => {
    const used = new Map<string, Set<string>>();
    const note = (name: string, where: string) => {
      if (!/^[A-Za-z_][\w-]*$/.test(name)) return;
      if (!used.has(name)) used.set(name, new Set());
      used.get(name)?.add(where);
    };
    for (const [path, source] of markupFiles) {
      for (const literal of classNameLiterals(source)) {
        for (const name of literal.split(/\s+/)) note(name, path);
      }
    }
    for (const [path, source] of legacyCssFiles) {
      for (const name of selectorClasses(source)) note(name, path);
    }
    expect(used.size).toBeGreaterThan(100);

    const css = await buildUtilities([...used.keys()]);
    const collisions = [...used]
      .filter(([name]) => generatesClass(css, name))
      .map(([name, where]) => `${name} (${[...where].join(", ")})`);
    expect(collisions, "legacy class names that Tailwind also generates").toEqual([]);
  });
});
