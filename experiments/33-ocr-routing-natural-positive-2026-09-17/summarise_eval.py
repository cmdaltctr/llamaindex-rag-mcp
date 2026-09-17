"""Experiment 33 Stage A measurements (tasks 4.2-4.4).

Scores ``output/routing.json`` against the frozen ``labels.json`` exactly as
``plan.json`` ``measurements`` defines, and applies the preregistered
decision rule. Writes ``output/arm_<arm>/eval_results.summary.json`` per arm and
``output/arm_comparison.json`` when both arms have run.

Reader-quality loss needs the local fast-path extractions and reference
transcriptions (gitignored); only scores reach the summary.

    uv run python experiments/33-ocr-routing-natural-positive-2026-09-17/summarise_eval.py
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP_DIR))

from build_labels import TRANSCRIPTS_DIR, recall, tokens  # noqa: E402

OUT_DIR = EXP_DIR / "output"
ARMS = ("sampled_baseline", "full_scan_candidate")
COMPARISON = OUT_DIR / "arm_comparison.json"
BEST_SECONDS_PER_PAGE = 33.7
WORST_SECONDS_PER_PAGE = 106.4
READER_LOSS_BELOW = 0.80


def wilson(successes: int, total: int, z: float = 1.96) -> list[float] | None:
    """Wilson score interval for a binomial proportion."""
    if total == 0:
        return None
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return [round(centre - half, 4), round(centre + half, 4)]


def confusion(rows: list[dict], label_of: dict[str, str]) -> dict:
    """Primary and secondary routing counts over needs_ocr / usable documents."""
    scored = [r for r in rows if label_of[r["doc_id"]] in {"needs_ocr", "usable"}]
    tp = [r for r in scored if label_of[r["doc_id"]] == "needs_ocr" and r["ocr_required"]]
    fn = [r for r in scored if label_of[r["doc_id"]] == "needs_ocr" and not r["ocr_required"]]
    fp = [r for r in scored if label_of[r["doc_id"]] == "usable" and r["ocr_required"]]
    tn = [r for r in scored if label_of[r["doc_id"]] == "usable" and not r["ocr_required"]]
    positives = len(tp) + len(fn)
    routed = len(tp) + len(fp)
    usable = len(fp) + len(tn)
    return {
        "documents_scored": len(scored),
        "needs_ocr_documents": positives,
        "usable_documents": usable,
        "true_positive": len(tp),
        "false_negative_count": len(fn),
        "false_positive_count": len(fp),
        "true_negative": len(tn),
        "routing_recall": round(len(tp) / positives, 4) if positives else None,
        "routing_recall_wilson95": wilson(len(tp), positives),
        "routing_precision": round(len(tp) / routed, 4) if routed else None,
        "false_positive_rate": round(len(fp) / usable, 4) if usable else None,
        "false_negative_ids": [r["doc_id"] for r in fn],
        "false_positive_ids": [r["doc_id"] for r in fp],
    }


def _reference_tokens(doc_id: str) -> list[str]:
    reference: list[str] = []
    for path in sorted((TRANSCRIPTS_DIR / doc_id).glob("p*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("legibility") == "legible":
            reference += tokens(record.get("transcription") or "")
    return reference


def reader_quality(rows: list[dict], arm_dir: Path) -> list[dict]:
    """Token recall of every fast-path extraction against the legible reference."""
    results = []
    for row in rows:
        if row["ocr_required"]:
            continue
        extraction = arm_dir / ".extractions" / f"{row['doc_id']}.txt"
        reference = _reference_tokens(row["doc_id"])
        score = recall(extraction.read_text(encoding="utf-8"), reference) if reference else None
        results.append(
            {
                "doc_id": row["doc_id"],
                "stratum": row["stratum"],
                "fast_path_token_recall": None if score is None else round(score, 4),
                "reader_quality_loss": score is not None and score < READER_LOSS_BELOW,
                "attributed_to": row.get("extraction_fallback_backend") or "pdf_inspector",
            }
        )
    return results


def summarise_arm(arm: str) -> dict | None:
    """Compute one arm's Stage A summary and preregistered decision."""
    arm_dir = OUT_DIR / f"arm_{arm}"
    labels = json.loads((EXP_DIR / "labels.json").read_text(encoding="utf-8"))
    if not labels.get("frozen"):
        print("labels.json is not frozen; refusing to score", file=sys.stderr)
        return None
    routing = json.loads((arm_dir / "routing.json").read_text(encoding="utf-8"))
    evidence = json.loads((OUT_DIR / "page_evidence.json").read_text(encoding="utf-8"))["pages"]

    documents = labels["documents"]
    label_of = {doc_id: doc["label"] for doc_id, doc in documents.items()}
    errors = [r for r in routing["rows"] if r.get("error_class")]
    rows = [r for r in routing["rows"] if not r.get("error_class")]

    primary = confusion(rows, label_of)
    usable_pages = Counter(p["doc_id"] for p in evidence if p["label"] == "usable")
    needs_pages = Counter(p["doc_id"] for p in evidence if p["label"] == "needs_ocr")
    routed_rows = [r for r in rows if r["ocr_required"]]
    routed_pages = sum(documents[r["doc_id"]]["pages"] for r in routed_rows)

    by_stratum: dict[str, Counter] = {}
    for row in routing["rows"]:
        outcome = (
            "read_error"
            if row.get("error_class")
            else ("routed" if row["ocr_required"] else "fast_path")
        )
        key = f"{label_of[row['doc_id']]}/{outcome}"
        by_stratum.setdefault(row["stratum"], Counter())[key] += 1

    ambiguous_ids = [d for d, label in label_of.items() if label == "ambiguous"]
    as_needs = {**label_of, **{d: "needs_ocr" for d in ambiguous_ids}}
    as_usable = {**label_of, **{d: "usable" for d in ambiguous_ids}}

    false_negative_detail = [
        {
            "doc_id": r["doc_id"],
            "stratum": r["stratum"],
            "pdf_type": r["pdf_type"],
            "pdf_confidence": r["pdf_confidence"],
            "pages_needing_ocr": r["pages_needing_ocr"],
            "pages_needing_ocr_before_fallback": r["pages_needing_ocr_before_fallback"],
            "extraction_fallback_backend": r["extraction_fallback_backend"],
            "needs_ocr_pages_at_risk": needs_pages[r["doc_id"]],
            "pages": documents[r["doc_id"]]["pages"],
        }
        for r in rows
        if r["doc_id"] in primary["false_negative_ids"]
    ]

    triggers = []
    if primary["needs_ocr_documents"] == 0:
        verdict = "INCOMPLETE"
    else:
        verdict = "EVALUABLE"
    if primary["false_negative_count"] >= 1:
        triggers.append("false_negative_trigger")
    born_digital_fp = [
        d for d in primary["false_positive_ids"] if documents[d]["stratum"] == "born_digital"
    ]
    if born_digital_fp:
        triggers.append("false_positive_trigger")

    summary = {
        "experiment": EXP_DIR.name,
        "stage": "A",
        "verdict": verdict,
        "triggers_fired": triggers,
        "recommend_calibration_proposal": bool(triggers),
        "thresholds_changed": False,
        "read_errors": [{"doc_id": r["doc_id"], "error_class": r["error_class"]} for r in errors],
        "primary": {
            k: primary[k]
            for k in (
                "needs_ocr_documents",
                "routing_recall",
                "routing_recall_wilson95",
                "false_negative_count",
                "false_negative_ids",
            )
        },
        "false_negative_detail": false_negative_detail,
        "secondary": {
            "routing_precision": primary["routing_precision"],
            "false_positive_count": primary["false_positive_count"],
            "false_positive_rate": primary["false_positive_rate"],
            "false_positive_ids": primary["false_positive_ids"],
            "born_digital_false_positive_ids": born_digital_fp,
            "unnecessary_ocr_pages": sum(usable_pages[r["doc_id"]] for r in routed_rows),
            "routed_documents": len(routed_rows),
            "routed_pages": routed_pages,
            "projected_ocr_seconds": {
                "label": "PROJECTION — no OCR ran",
                "best": round(routed_pages * BEST_SECONDS_PER_PAGE, 1),
                "worst": round(routed_pages * WORST_SECONDS_PER_PAGE, 1),
            },
        },
        "by_stratum": {s: dict(c) for s, c in sorted(by_stratum.items())},
        "confusion": primary,
        "ambiguous_sensitivity": {
            "ambiguous_ids": ambiguous_ids,
            "as_needs_ocr": confusion(rows, as_needs),
            "as_usable": confusion(rows, as_usable),
        },
        "unrecoverable_routes": [
            {"doc_id": r["doc_id"], "stratum": r["stratum"], "ocr_required": r["ocr_required"]}
            for r in rows
            if label_of[r["doc_id"]] == "unrecoverable"
        ],
        "arm": arm,
        "reader_quality": reader_quality(rows, arm_dir),
        "read_seconds_total": round(sum(r["read_seconds"] for r in rows), 2),
        "run_identity": routing.get("run_identity"),
    }
    (arm_dir / "eval_results.summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {k: summary[k] for k in ("arm", "verdict", "triggers_fired", "primary")}, indent=2
        )
    )
    return summary


def arm_divergence(label_of: dict[str, str]) -> list[dict]:
    """Documents whose route differs between the two arms, with their labels."""
    routes = {}
    for arm in ARMS:
        rows = json.loads((OUT_DIR / f"arm_{arm}" / "routing.json").read_text(encoding="utf-8"))
        routes[arm] = {r["doc_id"]: r for r in rows["rows"]}
    divergent = []
    for doc_id, base in routes[ARMS[0]].items():
        candidate = routes[ARMS[1]][doc_id]
        if base.get("ocr_required") != candidate.get("ocr_required"):
            divergent.append(
                {
                    "doc_id": doc_id,
                    "stratum": base["stratum"],
                    "label": label_of[doc_id],
                    ARMS[0]: {k: base.get(k) for k in ("ocr_required", "pages_needing_ocr")},
                    ARMS[1]: {k: candidate.get(k) for k in ("ocr_required", "pages_needing_ocr")},
                }
            )
    return divergent


def main() -> int:
    """Summarise every arm with routing output, then compare the arms."""
    summaries = {}
    for arm in ARMS:
        if (OUT_DIR / f"arm_{arm}" / "routing.json").exists():
            summary = summarise_arm(arm)
            if summary is None:
                return 1
            summaries[arm] = summary
    if len(summaries) < len(ARMS):
        print(f"arms with routing output: {sorted(summaries)}; comparison skipped", file=sys.stderr)
        return 0 if summaries else 1
    labels = json.loads((EXP_DIR / "labels.json").read_text(encoding="utf-8"))["documents"]
    comparison = {
        "arms": {
            arm: {k: s["primary"][k] for k in ("routing_recall", "false_negative_count")}
            | {"false_positive_count": s["secondary"]["false_positive_count"]}
            | {"routed_pages": s["secondary"]["routed_pages"]}
            for arm, s in summaries.items()
        },
        "arm_divergence": arm_divergence({k: v["label"] for k, v in labels.items()}),
    }
    COMPARISON.write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(comparison["arms"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
