// Experiment 37 KaTeX check (gate G2 and the PaddleOCR-VL comparison).
//
//   bun experiments/37-.../check_katex.mjs --engine dots-mocr --runs E-maths,E-scan
//   bun experiments/37-.../check_katex.mjs --file katex_selftest.md   (self-test)
//
// KaTeX 0.16.22 lives in the gitignored katex/ folder (bun add katex@0.16.22).
// A formula is each $$...$$ block and each $...$ inline span. Each one renders
// with throwOnError: true and displayMode set per formula. The extraction is
// the protocol's reference logic, unchanged.
//
// Writes output/katex_<engine>.json (per page counts and every error).

import { createRequire } from "node:module";
import { readFileSync, writeFileSync, renameSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const katex = createRequire(join(here, "katex", "package.json"))("katex");
const EXPECTED = "0.16.22";
if (katex.version !== EXPECTED) {
  console.error(`KaTeX ${katex.version} found, ${EXPECTED} required`);
  process.exit(2);
}

function extract(text) {
  const formulas = [];
  text = text.replace(/\$\$([\s\S]*?)\$\$/g, (_, b) => {
    formulas.push({ display: true, body: b });
    return " ";
  });
  text.replace(/(?<![\\$])\$([^$\n]+?)\$(?!\$)/g, (_, b) => {
    formulas.push({ display: false, body: b });
    return "";
  });
  return formulas;
}

function check(text) {
  const formulas = extract(text);
  const errors = [];
  for (const f of formulas) {
    try {
      katex.renderToString(f.body, { displayMode: f.display, throwOnError: true, strict: "ignore" });
    } catch (e) {
      errors.push({ display: f.display, body: f.body.slice(0, 300), message: String(e.message).slice(0, 200) });
    }
  }
  return { formulas: formulas.length, errors };
}

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
);

if (args.file) {
  const r = check(readFileSync(args.file, "utf8"));
  console.log(JSON.stringify({ file: args.file, formulas: r.formulas, errors: r.errors.length, detail: r.errors }, null, 1));
  process.exit(0);
}

const engine = args.engine;
const runs = (args.runs || "E-maths,E-scan").split(",");
const statePath = join(here, "output", `ocr_state_${engine}.json`);
if (!engine || !existsSync(statePath)) {
  console.error(`need --engine with an existing ${statePath}`);
  process.exit(2);
}
const state = JSON.parse(readFileSync(statePath, "utf8"));
const eng = state.engines[engine];
const pages = {};
const totals = {};
for (const run of runs) {
  let formulas = 0;
  let errors = 0;
  let pagesWithFormulas = 0;
  let skipped = 0;
  for (const [key, entry] of Object.entries(eng.runs[run].pages)) {
    if (entry.status !== "ok") {
      skipped += 1;
      continue;
    }
    const [doc, page] = key.split(":");
    const path = join(here, "output", engine, doc, `p${String(page).padStart(3, "0")}.md`);
    const r = check(readFileSync(path, "utf8"));
    pages[`${run} ${key}`] = { formulas: r.formulas, errors: r.errors };
    formulas += r.formulas;
    errors += r.errors.length;
    if (r.formulas) pagesWithFormulas += 1;
  }
  totals[run] = { formulas, errors, pages_with_formulas: pagesWithFormulas, pages_not_ok_skipped: skipped };
}
const all = Object.values(totals).reduce(
  (a, t) => ({ formulas: a.formulas + t.formulas, errors: a.errors + t.errors }),
  { formulas: 0, errors: 0 },
);
const out = {
  engine,
  katex: katex.version,
  runs,
  rule: "each $$...$$ block and each $...$ inline span; throwOnError true; strict ignore",
  totals,
  overall: { ...all, error_rate: all.formulas ? +(all.errors / all.formulas).toFixed(4) : null },
  pages,
};
const target = join(here, "output", `katex_${engine}.json`);
writeFileSync(target + ".tmp", JSON.stringify(out, null, 1) + "\n");
renameSync(target + ".tmp", target);
console.log(JSON.stringify({ engine, katex: katex.version, totals, overall: out.overall }, null, 1));
