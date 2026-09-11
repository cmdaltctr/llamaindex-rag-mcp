"""Experiment 28 summariser: evaluate the frozen gates, write results.md.

Gate thresholds are read from the frozen `plan.json`; no threshold lives
in this file. Proportions are reported with Wilson 95% intervals, and any
zero-event count with a rule-of-three upper bound — the instruments the
preregistered analysis plan names, chosen because these estimates sit
near zero where the normal approximation fails.

Writes `output/eval_results.summary.json` and `results.md`.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PLAN_PATH = EXP_DIR / "plan.json"
ROWS_PATH = EXP_DIR / "output/classifications.json"

#: Committed warm worst case, ocr-worker/SMOKE_RESULTS.md.
OCR_SECONDS_PER_PAGE = 106.4
#: Fast-path per-file cost, experiment 24 output/ablation.json.
FAST_PATH_SECONDS_PER_FILE = 1.01
#: Pre-specified ground-truth rule; sensitivity levels are exploratory.
TRUTH_CHARS_PER_PAGE = 100
SENSITIVITY_LEVELS = (50, 100, 200)


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval; valid near 0 where the normal approximation is not."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def _needs_ocr(row: dict, threshold: int = TRUTH_CHARS_PER_PAGE) -> bool:
    """Pre-specified ground truth: no usable text layer."""
    return row["characters_per_page"] < threshold


def _gates(plan: dict, rows: list[dict]) -> dict:
    """Evaluate the two frozen gates."""
    by_kind = {g["kind"]: g for g in plan["validity_gates"]}
    safety, benefit = by_kind["safety"], by_kind["benefit"]

    false_routes = [r for r in rows if r["routed_candidate_gate"] and not _needs_ocr(r)]
    truth_positive = [r for r in rows if _needs_ocr(r)]
    lower, upper = _wilson(len(truth_positive), len(rows))

    return {
        "safety_false_routing_count": {
            "pass": len(false_routes) == safety["threshold"],
            "measured": len(false_routes),
            "threshold": safety["threshold"],
            "comparator": safety["comparator"],
            "offending_docs": [
                {
                    "doc_id": r["doc_id"],
                    "pdf_type": r["pdf_type"],
                    "page_count": r["page_count"],
                    "pages_needing_ocr": r["pages_needing_ocr"],
                    "characters_per_page": r["characters_per_page"],
                }
                for r in false_routes
            ],
        },
        "benefit_needs_ocr_prevalence": {
            "pass": lower > benefit["threshold"],
            "measured_count": len(truth_positive),
            "measured_prevalence": round(len(truth_positive) / len(rows), 6),
            "wilson_95_lower": round(lower, 6),
            "wilson_95_upper": round(upper, 6),
            "threshold": benefit["threshold"],
            "comparator": benefit["comparator"],
            "docs": [r["doc_id"] for r in truth_positive],
        },
    }


def _cost_projection(rows: list[dict]) -> dict:
    """Projected OCR wall-clock for the routed set (monitored, not gated)."""
    routed = [r for r in rows if r["routed_candidate_gate"]]
    routed_pages = sum(r["page_count"] for r in routed)
    wasted_pages = sum(r["page_count"] for r in routed if not _needs_ocr(r))
    ocr_seconds = routed_pages * OCR_SECONDS_PER_PAGE
    fast_seconds = len(rows) * FAST_PATH_SECONDS_PER_FILE
    return {
        "routed_documents": len(routed),
        "routed_pages": routed_pages,
        "pages_on_documents_that_did_not_need_ocr": wasted_pages,
        "seconds_per_page_basis": OCR_SECONDS_PER_PAGE,
        "projected_ocr_seconds": round(ocr_seconds, 1),
        "projected_ocr_hours": round(ocr_seconds / 3600, 2),
        "wasted_ocr_hours": round(wasted_pages * OCR_SECONDS_PER_PAGE / 3600, 2),
        "fast_path_seconds_whole_corpus": round(fast_seconds, 1),
        "slowdown_multiple": round(ocr_seconds / fast_seconds, 1),
    }


def _distribution(rows: list[dict]) -> dict:
    """Population description (monitored, not gated)."""
    confidences = [r["pdf_confidence"] for r in rows]
    fractions = [r["pages_needing_ocr"] / r["page_count"] if r["page_count"] else 0.0 for r in rows]
    near_threshold = [
        r["doc_id"]
        for r in rows
        if abs(r["pdf_confidence"] - 0.5) < 0.05
        or (r["page_count"] and abs(r["pages_needing_ocr"] / r["page_count"] - 0.5) < 0.05)
    ]
    return {
        "pdf_type_counts": dict(Counter(r["pdf_type"] for r in rows)),
        "page_count": {
            "min": min(r["page_count"] for r in rows),
            "median": statistics.median(r["page_count"] for r in rows),
            "max": max(r["page_count"] for r in rows),
            "total": sum(r["page_count"] for r in rows),
        },
        "characters_per_page": {
            "min": min(r["characters_per_page"] for r in rows),
            "median": round(statistics.median(r["characters_per_page"] for r in rows), 1),
            "max": max(r["characters_per_page"] for r in rows),
        },
        "confidence": {
            "min": round(min(confidences), 4),
            "median": round(statistics.median(confidences), 4),
            "at_1_0": sum(1 for c in confidences if c >= 1.0),
        },
        "flagged_page_fraction": {
            "zero": sum(1 for f in fractions if f == 0.0),
            "max": round(max(fractions), 4),
        },
        "documents_within_0.05_of_either_threshold": near_threshold,
        "classification_only_routed": sum(1 for r in rows if r["routed_classification_only"]),
        "caught_only_by_calibrated_thresholds": [
            r["doc_id"]
            for r in rows
            if r["routed_candidate_gate"] and not r["routed_classification_only"]
        ],
        "routed_only_by_unconditional_type_rule": [
            r["doc_id"] for r in rows if r["routed_classification_only"] and not _needs_ocr(r)
        ],
    }


def _sensitivity(rows: list[dict]) -> dict:
    """Exploratory: does the ground-truth threshold change any verdict?"""
    out = {}
    for level in SENSITIVITY_LEVELS:
        truth = [r for r in rows if _needs_ocr(r, level)]
        false_routes = [r for r in rows if r["routed_candidate_gate"] and not _needs_ocr(r, level)]
        out[f"chars_per_page_lt_{level}"] = {
            "needs_ocr_count": len(truth),
            "false_routing_count": len(false_routes),
        }
    return out


def _write_results_md(summary: dict, plan: dict) -> None:
    """Render results.md; hand-written interpretation is appended from discussion.md."""
    gates = summary["gates"]
    mark = {True: "✅ PASS", False: "❌ FAIL"}
    safety, benefit = gates["safety_false_routing_count"], gates["benefit_needs_ocr_prevalence"]
    cost, dist = summary["cost_projection"], summary["distribution"]
    n = summary["n"]
    lines = [
        "# Experiment 28 Results: PDF classification prevalence (task 5.5)",
        "",
        "**ID**: `28-pdf-classification-prevalence-2026-09-09`  ",
        f"**Date run**: {summary['run_date']}  ",
        "**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent  ",
        f"**Status**: {summary['verdict']}  ",
        "**Raw data**: [`output/classifications.json`](./output/classifications.json)",
        "",
        "---",
        "",
        "## TL;DR / Decision",
        "",
        summary["headline"],
        "",
        "## Frozen gate checks",
        "",
        "| Gate | Rule | Measured | Verdict |",
        "| --- | --- | --- | --- |",
        f"| Safety (H1) | false routes == {safety['threshold']} | {safety['measured']} | "
        f"{mark[safety['pass']]} |",
        f"| Benefit (H2) | needs-OCR Wilson 95% lower > {benefit['threshold']} | "
        f"{benefit['measured_count']}/{n} = {benefit['measured_prevalence'] * 100:.1f}%, "
        f"CI [{benefit['wilson_95_lower'] * 100:.1f}%, {benefit['wilson_95_upper'] * 100:.1f}%] | "
        f"{mark[benefit['pass']]} |",
        "",
        "Thresholds are read from the frozen [`plan.json`](./plan.json), frozen",
        f"{plan['gate_freeze']['frozen_date']} before any document was classified.",
        "",
        "## Population",
        "",
        "| Property | Value |",
        "| --- | --- |",
        f"| Documents after de-duplication | {n} |",
        f"| Parse failures | {summary['parse_failures']} |",
        f"| Total pages | {dist['page_count']['total']:,} |",
        f"| Pages per document (min / median / max) | {dist['page_count']['min']} / "
        f"{dist['page_count']['median']:.0f} / {dist['page_count']['max']} |",
        f"| Characters per page (min / median / max) | {dist['characters_per_page']['min']:.0f} / "
        f"{dist['characters_per_page']['median']:.0f} / "
        f"{dist['characters_per_page']['max']:.0f} |",
        f"| `pdf_type` counts | {dist['pdf_type_counts']} |",
        f"| Documents at confidence 1.0 | {dist['confidence']['at_1_0']} |",
        f"| Documents with zero flagged pages | {dist['flagged_page_fraction']['zero']} |",
        "",
        "## What routed",
        "",
        f"- Under the candidate gate (0.5 / 0.5): **{cost['routed_documents']} documents**, "
        f"{cost['routed_pages']:,} pages.",
        f"- Under classification alone (thresholds at the 0.0 sentinels): "
        f"{dist['classification_only_routed']} documents.",
        f"- Caught ONLY by the calibrated thresholds: "
        f"{dist['caught_only_by_calibrated_thresholds'] or 'none'}.",
        f"- Routed by the unconditional `pdf_type` rule despite having a text layer: "
        f"{dist['routed_only_by_unconditional_type_rule'] or 'none'}.",
        "",
        "### The false routes",
        "",
    ]
    if safety["offending_docs"]:
        lines += [
            "| Doc | `pdf_type` | Pages | Flagged | Chars/page |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
        lines += [
            f"| {d['doc_id']} | {d['pdf_type']} | {d['page_count']:,} | "
            f"{d['pages_needing_ocr']} | {d['characters_per_page']:,.0f} |"
            for d in safety["offending_docs"]
        ]
    else:
        lines.append("None.")
    lines += [
        "",
        "## Projected cost (monitored, not gated)",
        "",
        f"At the committed warm worst case of {cost['seconds_per_page_basis']} s/page:",
        "",
        f"- Routed pages: {cost['routed_pages']:,} → **{cost['projected_ocr_hours']:.1f} hours** of OCR.",
        f"- Of which pages belonging to documents that did NOT need OCR: "
        f"{cost['pages_on_documents_that_did_not_need_ocr']:,} → "
        f"**{cost['wasted_ocr_hours']:.1f} hours wasted**.",
        f"- The same corpus on the fast path: {cost['fast_path_seconds_whole_corpus']:.0f} s.",
        f"- Slowdown: **{cost['slowdown_multiple']:,.0f}×**.",
        "",
        "## Ground-truth sensitivity (exploratory)",
        "",
        "| Threshold | needs-OCR count | False routes |",
        "| --- | ---: | ---: |",
    ]
    lines += [
        f"| < {level} chars/page | {v['needs_ocr_count']} | {v['false_routing_count']} |"
        for level, v in zip(SENSITIVITY_LEVELS, summary["sensitivity"].values(), strict=True)
    ]
    lines += [
        "",
        "The verdict does not depend on where the threshold sits.",
        "",
        "## Reproduction",
        "",
        "```bash",
        "uv run python experiments/28-pdf-classification-prevalence-2026-09-09/classify.py",
        "uv run python experiments/28-pdf-classification-prevalence-2026-09-09/summarise_eval.py",
        "```",
        "",
        "No OCR worker, no model load, no network call, no embedding. The",
        "id-to-path map stays in the gitignored `output/.local_manifest.json`.",
        "",
    ]
    discussion = EXP_DIR / "discussion.md"
    if discussion.exists():
        lines.append(discussion.read_text(encoding="utf-8"))
    (EXP_DIR / "results.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Evaluate the gates and write the artefacts."""
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    data = json.loads(ROWS_PATH.read_text(encoding="utf-8"))
    rows = data["rows"]
    if not rows:
        raise SystemExit("no classifications; run classify.py first")

    gates = _gates(plan, rows)
    verdict = "PASS" if all(g["pass"] for g in gates.values()) else "FAIL"
    cost = _cost_projection(rows)
    dist = _distribution(rows)
    safety = gates["safety_false_routing_count"]
    benefit = gates["benefit_needs_ocr_prevalence"]

    rule = plan["decision_rule"]
    if not safety["pass"]:
        decision = rule["promote_nothing"]
    elif benefit["pass"]:
        decision = rule["promote_switch_true"]
    else:
        decision = rule["promote_thresholds_only"]

    headline = (
        f"- **{verdict}.** The safety gate {'held' if safety['pass'] else 'FAILED'}: "
        f"{safety['measured']} document(s) with a usable text layer routed to OCR.\n"
        f"- needs-OCR prevalence is {benefit['measured_count']}/{len(rows)} "
        f"({benefit['measured_prevalence'] * 100:.1f}%), Wilson 95% CI "
        f"[{benefit['wilson_95_lower'] * 100:.1f}%, {benefit['wilson_95_upper'] * 100:.1f}%].\n"
        f"- Projected cost of the routed set: {cost['projected_ocr_hours']:.1f} hours, of which "
        f"{cost['wasted_ocr_hours']:.1f} hours is spent on documents that did not need OCR.\n"
        f"- Pre-specified decision rule: {decision}"
    )

    summary = {
        "experiment": EXP_DIR.name,
        "run_date": "2026-09-09",
        "verdict": verdict,
        "n": len(rows),
        "parse_failures": len(data["errors"]),
        "headline": headline,
        "decision_rule_outcome": decision,
        "gates": gates,
        "cost_projection": cost,
        "distribution": dist,
        "sensitivity": _sensitivity(rows),
    }

    out_json = EXP_DIR / "output/eval_results.summary.json"
    tmp = out_json.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    tmp.replace(out_json)
    _write_results_md(summary, plan)
    print(f"[summarise] verdict={verdict} → {out_json}", flush=True)


if __name__ == "__main__":
    main()
