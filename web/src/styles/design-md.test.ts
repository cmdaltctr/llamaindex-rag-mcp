/**
 * Keeps web/DESIGN.md in step with tokens.css. DESIGN.md is a portable summary
 * and tokens.css is the source of truth, so every colour, size, radius and
 * spacing value in the DESIGN.md front matter must equal the light-theme value
 * in tokens.css. Dark values live in prose and are not compared here.
 *
 * `compare` is pure (text in, mismatch messages out). The real files must give
 * an empty list. Mutated in-memory copies of either file must give a non-empty
 * list, which proves the guard fires when one file changes alone.
 *
 * The front matter uses a small YAML subset (nested maps, scalars, one folded
 * block). The `yaml` package is only a transitive dependency, so this file
 * carries a purpose-built parser instead of importing it.
 */
import { describe, expect, it } from "vitest";
import designMd from "../../DESIGN.md?raw";
import tokensCss from "./tokens.css?raw";

type Tokens = Record<string, string>;
type Node = { [key: string]: Node | string };
type Rgba = [number, number, number, number];

/** DESIGN.md colour key -> tokens.css custom property. New keys must be added here. */
const COLOUR_TOKENS: Record<string, string> = {
  primary: "accent",
  "primary-hover": "accent-hover",
  "primary-active": "accent-active",
  "primary-label": "accent-label",
  "primary-tint": "accent-tint",
  "primary-tint-hover": "accent-tint-hover",
  "primary-tint-active": "accent-tint-active",
  "primary-tint-border": "accent-tint-border",
  neutral: "surface-canvas",
  "surface-elevated": "surface-elevated",
  "surface-muted": "surface-muted",
  "text-primary": "text-primary",
  "text-secondary": "text-secondary",
  border: "border",
  "border-hover": "border-hover",
  selection: "selection",
  "focus-ring": "focus-ring",
  "status-error": "status-error",
  "status-warning": "status-warning",
  "status-success": "status-success",
  "status-info": "status-info",
  "status-error-label": "status-error-label",
  "status-warning-label": "status-warning-label",
  "status-success-label": "status-success-label",
  "status-info-label": "status-info-label",
};

/** DESIGN.md typography role -> tokens.css font-size property. */
const TYPE_TOKENS: Record<string, string> = {
  "page-title": "text-page-title",
  "section-title": "text-section-title",
  "subsection-title": "text-subsection-title",
  ui: "text-ui",
  meta: "text-meta",
  code: "text-code",
};

/** DESIGN.md typography role -> font stack property that must contain its fontFamily. */
const TYPE_FAMILY_TOKEN = (role: string): string => (role === "code" ? "font-mono" : "font-sans");

const RADIUS_TOKENS: Record<string, string> = {
  small: "radius-small",
  control: "radius-control",
  panel: "radius-panel",
};

/** Non-numeric spacing keys. Numeric keys map to `--space-<key>`. */
const NAMED_SPACING_TOKENS: Record<string, string> = {
  "control-height": "control-height",
  "control-height-small": "control-height-small",
  "touch-target": "touch-target",
};

// ---------- front matter parser (YAML subset) ----------

function unquote(raw: string): string {
  const v = raw.trim();
  return v.length >= 2 && v.startsWith('"') && v.endsWith('"') ? v.slice(1, -1) : v;
}

function parseFrontMatter(md: string): Node {
  const block = /^---\r?\n([\s\S]*?)\r?\n---/.exec(md)?.[1];
  if (block === undefined) throw new Error("DESIGN.md has no front matter");
  const root: Node = {};
  const stack: { indent: number; node: Node }[] = [{ indent: -1, node: root }];
  const lines = block.split(/\r?\n/);
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i] as string;
    const text = line.trim();
    if (text === "" || text.startsWith("#")) continue;
    const indent = line.length - line.trimStart().length;
    const m = /^(?:"([^"]+)"|([\w-]+)):\s*(.*)$/.exec(text);
    if (!m) throw new Error(`Cannot parse front matter line: ${line}`);
    const key = (m[1] ?? m[2]) as string;
    const rest = m[3] as string;
    while (stack.length > 1 && indent <= (stack[stack.length - 1] as { indent: number }).indent) stack.pop();
    const parent = (stack[stack.length - 1] as { node: Node }).node;
    if (rest === "") {
      const child: Node = {};
      parent[key] = child;
      stack.push({ indent, node: child });
    } else if (/^[>|][+-]?$/.test(rest)) {
      while (i + 1 < lines.length) {
        const next = lines[i + 1] as string;
        if (next.trim() !== "" && next.length - next.trimStart().length <= indent) break;
        i += 1;
      }
      parent[key] = "";
    } else {
      parent[key] = unquote(rest);
    }
  }
  return root;
}

function group(doc: Node, name: string): Record<string, string> {
  const g = doc[name];
  if (typeof g !== "object" || g === null) return {};
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(g)) if (typeof v === "string") out[k] = v;
  return out;
}

// ---------- tokens.css (light theme) ----------

function lightTokens(css: string): Tokens {
  const stripped = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const block = /:root\s*\{([^}]*)\}/.exec(stripped)?.[1] ?? "";
  const out: Tokens = {};
  for (const m of block.matchAll(/--([\w-]+):\s*([^;]+);/g)) out[m[1] as string] = (m[2] as string).trim();
  return out;
}

// ---------- value normalisation ----------

function parseColour(value: string, tokens: Tokens, depth = 0): Rgba | null {
  const v = value.trim();
  if (depth > 5) return null;
  const ref = /^var\(--([\w-]+)\)$/.exec(v);
  if (ref) {
    const target = tokens[ref[1] as string];
    return target === undefined ? null : parseColour(target, tokens, depth + 1);
  }
  const mixed = /^color-mix\(in srgb,\s*(var\(--[\w-]+\))\s+(\d+)%,\s*(var\(--[\w-]+\))\)$/.exec(v);
  if (mixed) {
    const a = parseColour(mixed[1] as string, tokens, depth + 1);
    const b = parseColour(mixed[3] as string, tokens, depth + 1);
    if (!a || !b) return null;
    const w = Number(mixed[2]) / 100;
    return [0, 1, 2, 3].map((i) => (a[i] as number) * w + (b[i] as number) * (1 - w)) as Rgba;
  }
  const hex = /^#([0-9a-f]{6})([0-9a-f]{2})?$/i.exec(v);
  if (hex) {
    const n = parseInt(hex[1] as string, 16);
    const alpha = hex[2] ? parseInt(hex[2], 16) / 255 : 1;
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255, alpha];
  }
  const fn = /^rgb\(\s*(\d+)\s+(\d+)\s+(\d+)\s*(?:\/\s*([\d.]+))?\s*\)$/.exec(v);
  if (fn) return [Number(fn[1]), Number(fn[2]), Number(fn[3]), fn[4] === undefined ? 1 : Number(fn[4])];
  return null;
}

function toPx(value: string): number | null {
  const m = /^(-?[\d.]+)(px|rem)$/.exec(value.trim());
  if (!m) return null;
  return Number(m[1]) * (m[2] === "rem" ? 16 : 1);
}

// ---------- the comparison ----------

function compare(designText: string, tokensText: string): string[] {
  const errors: string[] = [];
  const tokens = lightTokens(tokensText);
  if (Object.keys(tokens).length < 10) return ["tokens.css: light :root block not found or empty"];
  const doc = parseFrontMatter(designText);

  const token = (name: string, label: string): string | undefined => {
    const v = tokens[name];
    if (v === undefined) errors.push(`${label}: tokens.css has no --${name}`);
    return v;
  };

  const colours = group(doc, "colors");
  for (const [key, designValue] of Object.entries(colours)) {
    const name = COLOUR_TOKENS[key];
    if (name === undefined) {
      errors.push(`colors.${key}: no mapping to a tokens.css property (add it to COLOUR_TOKENS)`);
      continue;
    }
    const tokenValue = token(name, `colors.${key}`);
    if (tokenValue === undefined) continue;
    const want = parseColour(tokenValue, tokens);
    const got = parseColour(designValue, tokens);
    if (!want || !got) {
      errors.push(`colors.${key}: cannot read "${designValue}" or --${name} "${tokenValue}" as a colour`);
      continue;
    }
    const tolerance = tokenValue.startsWith("color-mix(") ? 1 : 0;
    const channelsDiffer = [0, 1, 2].some((i) => Math.abs((want[i] as number) - (got[i] as number)) > tolerance);
    if (channelsDiffer || Math.abs(want[3] - got[3]) > 0.005) {
      errors.push(`colors.${key}: DESIGN.md "${designValue}" differs from --${name} "${tokenValue}"`);
    }
  }
  for (const key of Object.keys(COLOUR_TOKENS)) {
    if (!(key in colours)) errors.push(`colors.${key}: mapped but missing from DESIGN.md`);
  }

  const sizeCheck = (label: string, designValue: string, name: string): void => {
    const tokenValue = token(name, label);
    if (tokenValue === undefined) return;
    const got = toPx(designValue);
    const want = toPx(tokenValue);
    if (got === null || want === null) errors.push(`${label}: cannot read "${designValue}" or --${name} "${tokenValue}" as a size`);
    else if (Math.abs(got - want) > 0.01) errors.push(`${label}: DESIGN.md "${designValue}" differs from --${name} "${tokenValue}"`);
  };

  const typography = doc.typography;
  const roles = typeof typography === "object" ? typography : {};
  for (const [role, spec] of Object.entries(roles)) {
    const name = TYPE_TOKENS[role];
    if (name === undefined || typeof spec !== "object") {
      errors.push(`typography.${role}: no mapping to a tokens.css property (add it to TYPE_TOKENS)`);
      continue;
    }
    if (typeof spec["fontSize"] === "string") sizeCheck(`typography.${role}.fontSize`, spec["fontSize"], name);
    else errors.push(`typography.${role}: fontSize missing`);
    const family = spec["fontFamily"];
    const stack = tokens[TYPE_FAMILY_TOKEN(role)] ?? "";
    if (typeof family !== "string" || !stack.split(",").some((f) => f.trim() === family)) {
      errors.push(`typography.${role}.fontFamily: "${String(family)}" is not in --${TYPE_FAMILY_TOKEN(role)}`);
    }
    // tokens.css defines no weight or line height, so only check the shape.
    if (!/^\d{3}$/.test(String(spec["fontWeight"]))) errors.push(`typography.${role}.fontWeight: not a numeric weight`);
    if (!(Number(spec["lineHeight"]) > 0)) errors.push(`typography.${role}.lineHeight: not a positive number`);
  }
  for (const role of Object.keys(TYPE_TOKENS)) {
    if (!(role in roles)) errors.push(`typography.${role}: mapped but missing from DESIGN.md`);
  }

  const rounded = group(doc, "rounded");
  for (const [key, value] of Object.entries(rounded)) {
    const name = RADIUS_TOKENS[key];
    if (name === undefined) errors.push(`rounded.${key}: no mapping to a tokens.css property (add it to RADIUS_TOKENS)`);
    else sizeCheck(`rounded.${key}`, value, name);
  }
  for (const key of Object.keys(RADIUS_TOKENS)) {
    if (!(key in rounded)) errors.push(`rounded.${key}: mapped but missing from DESIGN.md`);
  }

  const spacing = group(doc, "spacing");
  for (const [key, value] of Object.entries(spacing)) {
    const name = /^\d+$/.test(key) ? `space-${key}` : NAMED_SPACING_TOKENS[key];
    if (name === undefined) errors.push(`spacing.${key}: no mapping to a tokens.css property (add it to NAMED_SPACING_TOKENS)`);
    else sizeCheck(`spacing.${key}`, value, name);
  }
  for (const key of Object.keys(NAMED_SPACING_TOKENS)) {
    if (!(key in spacing)) errors.push(`spacing.${key}: mapped but missing from DESIGN.md`);
  }

  // Component entries may only point at tokens that exist, and heights follow the control height.
  const components = doc.components;
  for (const [cname, spec] of Object.entries(typeof components === "object" ? components : {})) {
    if (typeof spec !== "object") continue;
    for (const [prop, value] of Object.entries(spec)) {
      if (typeof value !== "string") continue;
      const ref = /^\{(\w+)\.([\w-]+)\}$/.exec(value);
      if (ref && !(ref[2] as string in (typeof doc[ref[1] as string] === "object" ? (doc[ref[1] as string] as Node) : {}))) {
        errors.push(`components.${cname}.${prop}: "${value}" points at a missing token`);
      }
      if (prop === "height") sizeCheck(`components.${cname}.height`, value, "control-height");
    }
  }
  return errors;
}

// ---------- tests ----------

function mutate(text: string, from: string, to: string): string {
  expect(text.split(from).length, `"${from}" occurs exactly once`).toBe(2);
  return text.replace(from, to);
}

describe("DESIGN.md front matter against tokens.css (light theme)", () => {
  it("parses the front matter sections", () => {
    const doc = parseFrontMatter(designMd);
    for (const name of ["colors", "typography", "rounded", "spacing", "components"]) {
      expect(Object.keys(typeof doc[name] === "object" ? (doc[name] as Node) : {}).length, name).toBeGreaterThan(0);
    }
  });

  it("matches every colour, size, radius and spacing value", () => {
    expect(compare(designMd, tokensCss)).toEqual([]);
  });

  it("computes status labels from the 60/40 mix, not from a copied hex", () => {
    const tokens = lightTokens(tokensCss);
    expect(tokens["status-success-label"]).toMatch(/^color-mix\(/);
    const [r, g, b] = parseColour(tokens["status-success-label"] as string, tokens) as Rgba;
    // #5f8d3d at 60% over #393a34 at 40% -> #506c39 (the DESIGN.md value) within rounding.
    expect([Math.round(r), Math.round(g), Math.round(b)]).toEqual([0x50, 0x6c, 0x39]);
  });

  describe("fails when DESIGN.md changes alone", () => {
    it("reports a changed colour", () => {
      const out = compare(mutate(designMd, 'primary: "#b35017"', 'primary: "#b35018"'), tokensCss);
      expect(out.join("\n")).toMatch(/colors\.primary:/);
    });
    it("reports a changed status label", () => {
      const out = compare(mutate(designMd, 'status-success-label: "#506c39"', 'status-success-label: "#506c3c"'), tokensCss);
      expect(out.join("\n")).toMatch(/colors\.status-success-label:/);
    });
    it("reports a changed radius, spacing step and font size", () => {
      expect(compare(mutate(designMd, "control: 10px", "control: 11px"), tokensCss).join("\n")).toMatch(/rounded\.control/);
      expect(compare(mutate(designMd, '"4": 16px', '"4": 17px'), tokensCss).join("\n")).toMatch(/spacing\.4/);
      expect(compare(mutate(designMd, "fontSize: 0.875rem", "fontSize: 0.9rem"), tokensCss).join("\n")).toMatch(/typography\.ui/);
    });
    it("reports a colour key that has no mapping", () => {
      const out = compare(mutate(designMd, '  primary: "#b35017"\n', '  primary: "#b35017"\n  brand-new: "#000000"\n'), tokensCss);
      expect(out.join("\n")).toMatch(/colors\.brand-new: no mapping/);
    });
    it("reports a removed colour", () => {
      const out = compare(mutate(designMd, '  border-hover: "#cbc7c2"\n', ""), tokensCss);
      expect(out.join("\n")).toMatch(/colors\.border-hover: mapped but missing/);
    });
  });

  describe("fails when tokens.css changes alone", () => {
    it("reports a changed colour", () => {
      const out = compare(designMd, mutate(tokensCss, "--accent: #b35017;", "--accent: #b35018;"));
      expect(out.join("\n")).toMatch(/colors\.primary:/);
    });
    it("reports a changed status colour through its computed label", () => {
      const out = compare(designMd, mutate(tokensCss, "--status-error: #b7493f;", "--status-error: #d7493f;"));
      expect(out.join("\n")).toMatch(/colors\.status-error-label:/);
    });
    it("reports a changed label percentage", () => {
      const out = compare(designMd, mutate(tokensCss, "var(--status-info) 60%", "var(--status-info) 50%"));
      expect(out.join("\n")).toMatch(/colors\.status-info-label:/);
    });
    it("reports a changed radius, spacing step and font size", () => {
      expect(compare(designMd, mutate(tokensCss, "--radius-panel: 12px;", "--radius-panel: 14px;")).join("\n")).toMatch(/rounded\.panel/);
      expect(compare(designMd, mutate(tokensCss, "--space-6: 1.5rem;", "--space-6: 1.75rem;")).join("\n")).toMatch(/spacing\.6/);
      expect(compare(designMd, mutate(tokensCss, "--text-meta: 0.8125rem;", "--text-meta: 0.85rem;")).join("\n")).toMatch(/typography\.meta/);
      expect(compare(designMd, mutate(tokensCss, "--touch-target: 2.75rem;", "--touch-target: 3rem;")).join("\n")).toMatch(/spacing\.touch-target/);
    });
  });

  it("ignores dark-theme edits, because DESIGN.md holds the light theme", () => {
    const edited = tokensCss.replaceAll("--accent: #da7c47;", "--accent: #da7c48;");
    expect(edited).not.toBe(tokensCss);
    expect(compare(designMd, edited)).toEqual([]);
  });
});
