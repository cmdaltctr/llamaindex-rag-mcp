"""Apply the frozen rescue signals to Experiment 33's saved local OCR text."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from experiment_io import (
    EXP_DIR,
    OUTPUT,
    approved_plan,
    atomic_json,
    load_token_rule,
    read_json,
    resume_payload,
    sha256,
    text_sha256,
    verify_freeze,
)
from signal_stats import auc_badness


def selected_candidates(summary: dict) -> list[str]:
    """Use the chosen signal, or both when the main verdict recommends neither."""
    return [summary["recommendation"]] if summary["recommendation"] else ["A", "B"]


def frozen_thresholds(summary: dict) -> dict[str, float]:
    """Reuse each signal's main equal-cost threshold without any local retuning."""
    return {
        name: summary["candidates"][name]["equal_cost_threshold"]
        for name in selected_candidates(summary)
    }


def population_metrics(rows: list[dict], threshold: float) -> dict:
    """Report bad-page ranking and flags at the unchanged decision threshold."""
    valid = [row for row in rows if row["body_recall"] is not None]
    bad = [row for row in valid if row["body_recall"] < 0.5]
    good = [row for row in valid if row["body_recall"] >= 0.5]
    caught = sum(row["score"] < threshold for row in bad)
    false = sum(row["score"] < threshold for row in good)
    return {
        "pages": len(valid),
        "bad_pages": len(bad),
        "bad_flagged": caught,
        "bad_recall": caught / len(bad) if bad else None,
        "good_pages": len(good),
        "good_flagged": false,
        "good_false_positive_rate": false / len(good) if good else None,
        "auc": auc_badness(valid),
        "threshold": threshold,
    }


def followup_metrics(payload: dict) -> dict:
    """Separate the 399 gated pages and io06, retaining per-document results."""
    results = {}
    for candidate, threshold in payload["thresholds"].items():
        rows = [
            {**row, "score": row["scores"][candidate]["score"]}
            for row in payload["rows"]
            if row["population"] == "gated"
        ]
        io06 = [row for row in rows if row["doc_id"] == "io06"]
        measured = population_metrics(rows, threshold)
        results[candidate] = {
            "gated": measured,
            "io06": population_metrics(io06, threshold),
            "documents": {
                doc_id: population_metrics(
                    [row for row in rows if row["doc_id"] == doc_id], threshold
                )
                for doc_id in sorted({row["doc_id"] for row in rows})
            },
            "experiment_39_chars_auc": 0.788,
            "reaches_followup_trigger": measured["auc"] is not None and measured["auc"] >= 0.8,
        }
    return results


def run(source: Path, resume: bool) -> None:
    """Score every saved text locally and checkpoint each completed document."""
    plan = approved_plan()
    verify_freeze(source)
    summary = read_json(OUTPUT / "summary.json")
    candidates = selected_candidates(summary)
    thresholds = frozen_thresholds(summary)
    source_path = source / "output" / "local_ocr" / "pages.json"
    source_rows = read_json(source_path)["rows"]
    gated = [row for row in source_rows if row["body_label"] == "needs_ocr"]
    io06 = [row for row in gated if row["doc_id"] == "io06"]
    if (
        len(source_rows) != 464
        or len(gated) != 399
        or len(io06) != 66
        or sum(row["body_recall"] < 0.5 for row in io06) != 13
    ):
        raise ValueError("local OCR population differs from the registered follow-up")
    paths = {
        (row["doc_id"], row["page"]): source
        / "output"
        / ".local_ocr_text"
        / row["doc_id"]
        / f"p{row['page']:03d}.md"
        for row in source_rows
    }
    manifest = {f"{doc_id}/p{page:03d}": sha256(path) for (doc_id, page), path in paths.items()}
    signal_hashes = {}
    for candidate in candidates:
        signal = EXP_DIR / ("candidate_a.py" if candidate == "A" else "julia_onnx.py")
        signal_hashes[candidate] = sha256(signal)
        main = read_json(OUTPUT / f"candidate_{candidate.lower()}.json")
        if main["identity"]["signal_sha256"] != signal_hashes[candidate]:
            raise ValueError("follow-up signal code differs from the main experiment")
    identity = {
        "source_rows_sha256": sha256(source_path),
        "source_text_sha256": manifest,
        "signal_sha256": signal_hashes,
        "thresholds": thresholds,
        "request": plan["candidates"]["B"]["request"],
        "runner_sha256": sha256(Path(__file__)),
    }
    target = OUTPUT / "local_text_signal.json"
    payload = resume_payload(target, identity, resume)
    payload["thresholds"] = thresholds
    rule = load_token_rule(source)
    model = None
    if "B" in candidates:
        from julia_onnx import JuliaRuntime

        model = JuliaRuntime(plan, require_parity=True)
    for doc_id in dict.fromkeys(row["doc_id"] for row in source_rows):
        if doc_id in payload["completed_documents"]:
            print(f"[resume local] {doc_id}", flush=True)
            continue
        results = []
        for row in source_rows:
            if row["doc_id"] != doc_id:
                continue
            text = paths[(doc_id, row["page"])].read_text(encoding="utf-8")
            scores = {}
            for candidate in candidates:
                start = time.process_time()
                if candidate == "A":
                    from candidate_a import score_a

                    score = score_a(text, rule)
                else:
                    score = {"score": model.probability(text)}
                score["cpu_seconds"] = time.process_time() - start
                scores[candidate] = score
            results.append(
                {
                    "doc_id": doc_id,
                    "page": row["page"],
                    "body_recall": row["body_recall"],
                    "population": "gated" if row["body_label"] == "needs_ocr" else "figure_only",
                    "text_sha256": text_sha256(text),
                    "scores": scores,
                }
            )
        payload["rows"].extend(results)
        payload["completed_documents"].append(doc_id)
        atomic_json(target, payload)
        print(f"[local text] {doc_id}: {len(results)} pages", flush=True)
    if (
        len(payload["rows"]) != 464
        or len({(r["doc_id"], r["page"]) for r in payload["rows"]}) != 464
    ):
        raise ValueError("local follow-up does not cover all 464 saved texts")
    print("[local text] complete: 464 saved pages", flush=True)


def main() -> None:
    """Read the frozen source location from runtime arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-exp", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run(args.source_exp.resolve(), args.resume)


if __name__ == "__main__":
    main()
