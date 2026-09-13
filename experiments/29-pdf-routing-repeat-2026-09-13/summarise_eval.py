"""Summarise experiment 29: policy comparison against independent labels.

Reads ``output/classifications.json`` (public rows) and the frozen
``labels.json`` (independent page assessment, doc_id keys only), evaluates
the frozen validity gates from ``plan.json`` and writes
``output/eval_results.summary.json`` plus a Markdown block for
``report.md``.

Labelling rules from the change spec:

- A ``development`` document's outcome is a regression check, never
  independent validation. Held-out rows decide the gates.
- ``needs_ocr`` may be ``true``, ``false`` or ``"uncertain"``; uncertain
  labels are reported explicitly and counted in neither numerator.
- A gate cannot be evaluated while ``labels.frozen`` is false or any
  held-out document is unlabelled.

OCR wall-clock figures are PROJECTIONS at the committed warm worst case
(106.4 s/page, from ocr-worker/SMOKE_RESULTS.md) unless the run was
separately authorised for real OCR — the authorisation block in
plan.json decides which wording the summary emits.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PLAN_PATH = EXP_DIR / "plan.json"
LABELS_PATH = EXP_DIR / "labels.json"
OUT_PATH = EXP_DIR / "output/classifications.json"
SUMMARY_PATH = EXP_DIR / "output/eval_results.summary.json"

WARM_WORST_SECONDS_PER_PAGE = 106.4
FAST_PATH_SECONDS_PER_FILE = 1.0


def _wilson95(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    z = 1.96
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _policy_table(rows: list[dict], labels: dict, routed_key: str, split: str) -> dict:
    subset = [r for r in rows if r["split"] == split]
    labelled = [r for r in subset if r["doc_id"] in labels]
    unlabelled = [r["doc_id"] for r in subset if r["doc_id"] not in labels]
    false_routes, missed, uncertain = [], [], []
    for row in labelled:
        truth = labels[row["doc_id"]].get("needs_ocr")
        routed = row[routed_key]
        if truth == "uncertain":
            uncertain.append(row["doc_id"])
            continue
        if routed and truth is False:
            false_routes.append(row["doc_id"])
        if not routed and truth is True:
            missed.append(row["doc_id"])
    routed_pages = sum(r["page_count"] for r in labelled if r[routed_key])
    return {
        "documents": len(subset),
        "labelled": len(labelled),
        "unlabelled": unlabelled,
        "routed": sum(1 for r in labelled if r[routed_key]),
        "false_routes": false_routes,
        "missed_needs_ocr": missed,
        "uncertain_labels": uncertain,
        "routed_pages": routed_pages,
        "projected_ocr_seconds": round(routed_pages * WARM_WORST_SECONDS_PER_PAGE, 1),
    }


def main() -> None:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    labels_doc = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    state = json.loads(OUT_PATH.read_text(encoding="utf-8"))

    labels = labels_doc.get("labels", {})
    rows = state["rows"]

    ocr_authorised = bool(plan.get("ocr_authorisation", {}).get("authorised"))

    summary: dict = {
        "experiment_id": plan["experiment_id"],
        "labels_frozen": bool(labels_doc.get("frozen")),
        "policies": {},
        "gates": [],
        "ocr_cost_basis": "measured" if ocr_authorised else "projected",
    }

    for policy in plan["policies"]:
        key = f"routed_{policy}"
        summary["policies"][policy] = {
            "development": _policy_table(rows, labels, key, "development"),
            "held_out": _policy_table(rows, labels, key, "held_out"),
        }

    held_out_unlabelled = [
        r["doc_id"] for r in rows if r["split"] == "held_out" and r["doc_id"] not in labels
    ]
    gates_evaluable = summary["labels_frozen"] and not held_out_unlabelled

    for gate in plan.get("validity_gates", []):
        metric = gate["metric"]
        held = summary["policies"]["candidate"]["held_out"]
        observed: float | str
        if metric == "false_routing_count":
            observed = len(held["false_routes"])
        elif metric == "missed_needs_ocr_count":
            observed = len(held["missed_needs_ocr"])
        else:
            observed = "unknown-metric"
        verdict = "not_evaluable"
        if gates_evaluable and isinstance(observed, (int, float)):
            ok = {
                "==": observed == gate["threshold"],
                ">": observed > gate["threshold"],
            }.get(gate["comparator"], False)
            verdict = "pass" if ok else "fail"
        summary["gates"].append(
            {
                "kind": gate["kind"],
                "metric": metric,
                "comparator": gate["comparator"],
                "threshold": gate["threshold"],
                "observed": observed,
                "verdict": verdict,
            }
        )

    needs_ocr_held_out = [
        doc_id
        for doc_id, label in labels.items()
        if label.get("needs_ocr") is True
        and any(r["doc_id"] == doc_id and r["split"] == "held_out" for r in rows)
    ]
    lo, hi = _wilson95(
        len(needs_ocr_held_out), summary["policies"]["candidate"]["held_out"]["labelled"]
    )
    summary["needs_ocr_prevalence_held_out"] = {
        "count": len(needs_ocr_held_out),
        "wilson95": [round(lo, 4), round(hi, 4)],
    }

    if not gates_evaluable:
        summary["gates_note"] = (
            "Gates not evaluated: labels not frozen or held-out documents unlabelled."
        )

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    basis = "measured" if ocr_authorised else "PROJECTED (no real OCR authorised)"
    print(f"[summary] gates_evaluable={gates_evaluable}  OCR cost basis: {basis}")
    for gate in summary["gates"]:
        print(f"  {gate['kind']}: {gate['verdict']} (observed {gate['observed']})")
    print(f"[summary] wrote {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
