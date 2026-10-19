import { describe, expect, it } from "vitest";

/**
 * Guard for the no-legacy rule of `redesign-web-workspace`: nothing from the
 * pre-redesign foundation may remain in `web/src`. Each rule names a symbol
 * or file shape that only old code uses.
 */
const sources = import.meta.glob<string>("/src/**/*.{ts,tsx,css}", { query: "?raw", import: "default", eager: true });

interface Rule {
  name: string;
  pattern: RegExp;
  /** Files where the pattern is allowed. */
  allowed?: (path: string) => boolean;
}

const isTestSupport = (path: string) => /\.test\.tsx?$/.test(path) || /\/test\//.test(path);

const RULES: Rule[] = [
  {
    name: "fetchImpl outside the API client, its provider, bootstrap and test support",
    pattern: /\bfetchImpl\b/,
    allowed: (path) => isTestSupport(path) || /\/api\/(ApiProvider\.tsx|client\.ts|bootstrap\.ts)$/.test(path),
  },
  { name: "retired helper names", pattern: /\b(useLoad|messageOf|getJson|sendJson|postJson|RequestOptions)\b/, allowed: (p) => /\/api\/client\.test\.ts$/.test(p) },
  { name: "retired client-side upload limit", pattern: /\b(MAX_UPLOAD_BYTES|UPLOAD_LIMIT_LABEL)\b/ },
  { name: "retired storage keys and state", pattern: /omrg-workspace-ui|omrg-canvas-session|inspectorOpen|readUiState|writeUiState|readSession|writeSession/, allowed: (p) => /\.test\.tsx?$/.test(p) },
  { name: "retired view modules", pattern: /views\/shared|views\/library|views\/search|views\/ask|views\/DocumentView/ },
  { name: "legacy class names", pattern: /className=\{?["'`][^"'`]*(?<![\w-])(button|button--\w+|control|control--\w+|panel|view|view__\w+|empty-state|app-nav|app-nav__\w+|topbar|field-inline|type-(page-title|section-title|meta|code))(?![\w-])/ },
  { name: "stylesheet other than tokens.css and app.css", pattern: /^[\s\S]*$/, allowed: (p) => !p.endsWith(".css") || /\/styles\/(tokens|app)\.css$/.test(p) },
];

function violations(): { rule: string; path: string }[] {
  const found: { rule: string; path: string }[] = [];
  for (const [path, text] of Object.entries(sources)) {
    if (path.endsWith("noLegacyResidue.test.ts")) continue;
    for (const rule of RULES) {
      if (rule.allowed?.(path)) continue;
      if (rule.pattern.test(text)) found.push({ rule: rule.name, path });
    }
  }
  return found;
}

describe("no legacy residue", () => {
  it("finds no legacy code in web/src", () => {
    expect(violations()).toEqual([]);
  });
});
