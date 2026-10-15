/**
 * Test helper: compile the real stylesheet entry (app.css) with Tailwind's
 * public `compile` API, without a bundler. jsdom applies no stylesheets, so
 * the token bridge and the layering rules can only be checked on CSS output.
 *
 * Only Tailwind's own files are loaded. Every other import (React Flow,
 * tw-animate-css) is stubbed as empty, because it adds no theme
 * keys and no utilities that the checks need.
 */
import { compile } from "tailwindcss";
import preflightCss from "tailwindcss/preflight.css?raw";
import themeCss from "tailwindcss/theme.css?raw";
import utilitiesCss from "tailwindcss/utilities.css?raw";
import appCss from "./app.css?raw";

const TAILWIND_FILES: Record<string, string> = {
  "tailwindcss/theme.css": themeCss,
  "tailwindcss/preflight.css": preflightCss,
  "tailwindcss/utilities.css": utilitiesCss,
};

/** Build the CSS that Tailwind generates for these class names. */
export async function buildUtilities(candidates: string[]): Promise<string> {
  const compiler = await compile(appCss, {
    base: "/",
    loadStylesheet: (id, base) =>
      Promise.resolve({ path: id, base, content: TAILWIND_FILES[id] ?? "" }),
  });
  return compiler.build(candidates);
}
