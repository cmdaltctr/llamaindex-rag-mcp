/**
 * Contrast and consistency checks on tokens.css. Raw status colours fail WCAG
 * AA (4.5:1) as normal text on their own tint, so badges use the
 * --status-*-label tokens. These tests compute the real ratios from the file,
 * in both themes, so a palette or percentage change cannot silently drop
 * below AA.
 */
import { describe, expect, it } from "vitest";
import tokensCss from "./tokens.css?raw";

const STATUSES = ["error", "warning", "success", "info"] as const;
const SURFACES = ["surface-canvas", "surface-elevated", "surface-muted"] as const;
/** Opacity of the status tint behind badge text (the `/10` in the Badge classes). */
const TINT_OPACITY = 0.1;

type Tokens = Record<string, string>;

const stripped = tokensCss.replace(/\/\*[\s\S]*?\*\//g, "");

function declarationsIn(block: string | undefined): Tokens {
  const out: Tokens = {};
  for (const m of (block ?? "").matchAll(/--([\w-]+):\s*([^;]+);/g)) out[m[1] as string] = (m[2] as string).trim();
  return out;
}

const light = declarationsIn(/:root\s*\{([^}]*)\}/.exec(stripped)?.[1]);
const darkByAttribute = declarationsIn(/:root\[data-theme="dark"\]\s*\{([^}]*)\}/.exec(stripped)?.[1]);
const darkBySystem = declarationsIn(
  /@media \(prefers-color-scheme: dark\)\s*\{\s*:root:not\(\[data-theme="light"\]\)\s*\{([^}]*)\}/.exec(stripped)?.[1],
);

const themes: Record<string, Tokens> = {
  light,
  dark: { ...light, ...darkByAttribute },
};

type Rgb = [number, number, number];

function hex(value: string | undefined, name: string): Rgb {
  const m = /^#([0-9a-f]{6})$/i.exec(value ?? "");
  if (!m) throw new Error(`${name} is not a #rrggbb colour: ${value}`);
  const n = parseInt(m[1] as string, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

const mix = (a: Rgb, b: Rgb, weightA: number): Rgb =>
  [0, 1, 2].map((i) => (a[i] as number) * weightA + (b[i] as number) * (1 - weightA)) as Rgb;

function luminance([r, g, b]: Rgb): number {
  const lin = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

/** Status share of the label colour, read from the declaration in tokens.css. */
function labelShare(status: string): number {
  const value = light[`status-${status}-label`];
  const m = new RegExp(
    `^color-mix\\(in srgb, var\\(--status-${status}\\) (\\d+)%, var\\(--text-primary\\)\\)$`,
  ).exec(value ?? "");
  if (!m) throw new Error(`--status-${status}-label must mix var(--status-${status}) with var(--text-primary) in srgb: ${value}`);
  return Number(m[1]) / 100;
}

describe("status label contrast", () => {
  for (const [themeName, tokens] of Object.entries(themes)) {
    for (const status of STATUSES) {
      for (const surface of SURFACES) {
        it(`${status} label on its tint over ${surface} is at least 4.5:1 (${themeName})`, () => {
          const colour = hex(tokens[`status-${status}`], `status-${status}`);
          const text = hex(tokens["text-primary"], "text-primary");
          const surfaceColour = hex(tokens[surface], surface);
          const label = mix(colour, text, labelShare(status));
          const fill = mix(colour, surfaceColour, TINT_OPACITY);
          expect(contrast(label, fill)).toBeGreaterThanOrEqual(4.5);
        });
      }
    }
  }

  it("catches a raw status colour as badge text (the reason labels exist)", () => {
    // Success on its own tint over elevated is 3.28:1 in light. This keeps the
    // check honest: if the maths stopped failing for raw colours, it would be broken.
    const colour = hex(light["status-success"], "status-success");
    const fill = mix(colour, hex(light["surface-elevated"], "surface-elevated"), TINT_OPACITY);
    expect(contrast(colour, fill)).toBeLessThan(4.5);
  });
});

describe("theme blocks", () => {
  it("declare identical dark values for the attribute and the system preference", () => {
    expect(Object.keys(darkBySystem).length).toBeGreaterThan(10);
    expect(darkBySystem).toEqual(darkByAttribute);
  });

  it("declare every token that the dark theme overrides in the light theme too", () => {
    const missing = Object.keys(darkByAttribute).filter((name) => !(name in light));
    expect(missing).toEqual([]);
  });
});
