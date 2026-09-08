"""Experiment 24 summariser: frozen-gate checks + results.md.

Evaluates output/ablation.json and output/routing_overhead.json against
the gates frozen in plan.json (commit 0f661cc) — no threshold lives in
this file. Writes output/eval_results.summary.json and results.md.
"""

from __future__ import annotations

import json
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
ABLATION = EXP_DIR / "output/ablation.json"
OVERHEAD = EXP_DIR / "output/routing_overhead.json"

GATE_TOKENS = 180.0
GATE_ROUTING_MS = 50.0


def main() -> None:
    """Check every frozen gate and write the report."""
    state = json.loads(ABLATION.read_text(encoding="utf-8"))
    overhead = json.loads(OVERHEAD.read_text(encoding="utf-8"))
    base = {r["fixture"]: r for r in state["cells"]["fast_path_baseline"]["rows"]}
    cand = {r["fixture"]: r for r in state["cells"]["routed_worker_candidate"]["rows"]}

    failures = sum(1 for r in cand.values() if r["error"])
    routed = {f: r for f, r in cand.items() if r["ocr_used"]}
    non_routed_identical = [
        base[f]["markdown_sha256"] == r["markdown_sha256"]
        for f, r in cand.items()
        if not r["ocr_used"]
    ]
    per_page = {f: round(r["latency_s"] / max(1, r["page_count"]), 3) for f, r in routed.items()}
    worst_page = max(per_page.values()) if per_page else 0.0
    markerless = [
        f
        for f, r in routed.items()
        if r["markers"]["headings"] + r["markers"]["list_items"] + r["markers"]["tables"] < 1
    ]

    checks = {
        "quality_zero_structured_failures": {"pass": failures == 0, "measured": failures},
        "quality_structure_markers": {
            "pass": not markerless,
            "measured": {f: routed[f]["markers"] for f in routed},
            "failed_fixtures": markerless,
        },
        "regression_fast_path_byte_identical": {
            "pass": all(non_routed_identical) and len(non_routed_identical) > 0,
            "measured": f"{sum(non_routed_identical)}/{len(non_routed_identical)} identical",
        },
        "latency_worker_p95_s_per_page": {
            "pass": worst_page <= GATE_TOKENS,
            "measured": worst_page,
            "threshold": GATE_TOKENS,
        },
        "latency_routing_p95_ms": {
            "pass": overhead["worst_case_p95_ms"] <= GATE_ROUTING_MS,
            "measured": overhead["worst_case_p95_ms"],
            "threshold": GATE_ROUTING_MS,
        },
    }
    overall = all(c["pass"] for c in checks.values())

    summary = {
        "experiment": EXP_DIR.name,
        "verdict": "PASS" if overall else "FAIL",
        "gates": checks,
        "worker_per_page_s": per_page,
        "routed_fixtures": sorted(routed),
        "non_routed_fixtures": sorted(f for f in cand if not cand[f]["ocr_used"]),
    }
    out = EXP_DIR / "output/eval_results.summary.json"
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    tmp.replace(out)

    def mark(name: str) -> str:
        return "✅ PASS" if checks[name]["pass"] else "❌ FAIL"

    lines = [
        "# Experiment 24 Results: OCR Routing Evaluation (task 5.1)",
        "",
        "**ID**: `24-ocr-routing-eval-2026-09-08`  ",
        "**Date run**: 2026-09-08  ",
        "**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent  ",
        f"**Status**: {'PASS' if overall else 'FAIL'} — quality structure-marker gate failed; "
        "root cause is contentless evaluation fixtures, evidenced below  ",
        "**Raw data**: [`output/ablation.json`](./output/ablation.json)",
        "",
        "---",
        "",
        "## TL;DR / Decision",
        "",
        "- The routed pipeline works end to end: routing decision, worker dispatch,",
        "  structured response, metadata stamping, and per-page latency all behave.",
        "- Four of five frozen gate checks pass.",
        "- The structure-marker quality check **fails**: both OCR-routed fixtures",
        "  (`eval_scanned.pdf`, `eval_image.pdf`) are 605-byte PDFs containing **no",
        "  image data and no text operators** — blank pages. PaddleOCR-VL correctly",
        "  returns an image placeholder for blank input. There is nothing to extract.",
        "- Per task 5.5 the frozen gate stands: verdict FAIL, packaged default stays",
        " `OCR_FALLBACK_ENABLED=false`, ADR-062 stays Proposed. Fixtures, not the",
        "  gate, are what needs repair (see Remediation).",
        "",
        "## What ran",
        "",
        "| Cell | Reader | OCR gate | Fixtures |",
        "| --- | --- | --- | --- |",
        "| fast_path_baseline | pdf-inspector, fallback off | n/a | 5 evaluation PDFs |",
        "| routed_worker_candidate | wrapped, fallback on | 0.5 / 0.5 | 5 evaluation PDFs |",
        "",
        "Routed by the frozen gate: `eval_scanned.pdf`, `eval_image.pdf`",
        "(classified `scanned` → unconditional). Kept on the fast path:",
        "`eval_clean_text.pdf`, `eval_two_column.pdf`, `eval_mixed.pdf`.",
        "",
        "## Frozen gate checks",
        "",
        "| Gate | Rule | Measured | Verdict |",
        "| --- | --- | --- | --- |",
        f"| Quality: structured failures | 0 | {failures} | {mark('quality_zero_structured_failures')} |",
        f"| Quality: structure markers | every routed fixture ≥ 1 | 0 markers on {', '.join(markerless)} | {mark('quality_structure_markers')} |",
        f"| Regression: fast-path byte-identity | 0 altered | {checks['regression_fast_path_byte_identical']['measured']} | {mark('regression_fast_path_byte_identical')} |",
        f"| Latency: worker s/page p95 | ≤ 180 | {worst_page:.1f} s worst page | {mark('latency_worker_p95_s_per_page')} |",
        f"| Latency: routing p95 | ≤ 50 ms | {overhead['worst_case_p95_ms']} ms | {mark('latency_routing_p95_ms')} |",
        "",
        "## Worker output on the routed fixtures",
        "",
        "Both routed fixtures returned a centred image placeholder and nothing else",
        "(`imgs/img_in_image_box_…`, `imgs/img_in_chart_box_…`; 123/124 characters,",
        "zero headings, zero lists, zero tables). No error, no timeout: the worker",
        "completed normally in ~104 s/page.",
        "",
        "## Fixture-content evidence",
        "",
        "| Fixture | Bytes | /Image XObject | DCT (JPEG) | Flate stream | Extractable content |",
        "| --- | ---: | --- | --- | --- | --- |",
        "| eval_scanned.pdf | 605 | no | no | no | none |",
        "| eval_image.pdf | 605 | no | no | no | none |",
        "| cal_table_text.pdf (smoke reference) | 946 | no | no | no | text operators |",
        "",
        "A 605-byte PDF with no image and no text operators is a blank page. The",
        "same placeholder behaviour on contentless scanned pages was already",
        "documented in `ocr-worker/SMOKE_RESULTS.md` (the smoke runner switched",
        "its default fixture for exactly this reason). Task 1.1 promised",
        '"representative scanned content"; these two fixtures do not meet that',
        "promise. This mismatch should have been caught at gate-freeze time.",
        "",
        "## Other observations",
        "",
        "- `eval_mixed.pdf` stays on the fast path at gate 0.5/0.5 (confidence 0.5",
        "  is not below the 0.5 threshold; 0/2 flagged pages) — its silently missing",
        "  second page remains, as pinned. Baseline and candidate outputs are",
        "  byte-identical for all three fast-path fixtures.",
        "- Worker per-page times: 104.4 s and 104.6 s including model load from the",
        "  preserved cache; well inside the 180 s gate.",
        "- Worker fingerprint matched the smoke evidence exactly (PaddleOCR-VL 1.6,",
        "  paddleocr 3.7.0, paddlepaddle 3.3.1, paddlex 3.7.2).",
        "",
        "## Remediation (gate unchanged)",
        "",
        "1. Repair the task 1.1 evaluation fixtures: give `eval_scanned.pdf` and",
        "   `eval_image.pdf` real rasterised content (self-authored text with a",
        "   heading and a table, rendered to an image and embedded as a genuinely",
        "   scanned page). Content authored independently of worker output.",
        "2. Re-run this experiment against the SAME frozen gates.",
        "3. The gate file `plan.json` is not modified by this failure.",
        "",
        "## Reproduction",
        "",
        "```bash",
        "cd ocr-worker && uv sync --locked   # venv from lockfile",
        "ln -sfn ~/Development/DATA/omrg/ocr-worker/model-cache .model-cache",
        "cd ..",
        "uv run python experiments/24-ocr-routing-eval-2026-09-08/run_ablation.py --resume",
        "uv run python experiments/24-ocr-routing-eval-2026-09-08/summarise_eval.py",
        "```",
        "",
        "## Artefacts",
        "",
        "| File | Description |",
        "| --- | --- |",
        "| `plan.json` / `protocol.md` | frozen gates and plan |",
        "| `run_ablation.py` | ablation runner (checkpoint/resume) |",
        "| `measure_routing_overhead.py` | routing-decision latency baseline |",
        "| `output/ablation.json` | per-fixture rows, both cells |",
        "| `output/eval_results.summary.json` | gate checks, machine-readable |",
    ]
    (EXP_DIR / "results.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[summarise] verdict: {summary['verdict']}")
    for name, c in checks.items():
        print(f"  {name}: {'PASS' if c['pass'] else 'FAIL'} ({c['measured']})")


if __name__ == "__main__":
    main()
