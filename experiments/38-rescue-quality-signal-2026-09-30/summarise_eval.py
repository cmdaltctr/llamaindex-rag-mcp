"""Summarise candidate scores with the preregistered routing and adoption gates."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
from experiment_io import OUTPUT, approved_plan, atomic_json, read_json, sha256, verify_freeze
from score_signals import eligible_rows, verify_coverage
from signal_stats import bootstrap_interval, equal_cost_threshold, mcnemar, metrics


def recommend(a_passes: bool, b_passes: bool, delta: float, p_value: float) -> str | None:
    """Apply design D6 with the unchanged 0.10 margin and p below 0.05."""
    if b_passes and delta >= 0.10 and p_value < 0.05:
        return "B"
    return "A" if a_passes else None


def simulate_routing(
    rows: list[dict], baseline: list[dict], labels: dict, threshold: float
) -> dict:
    """Count flags only on the shipped rescue tier, preserving prior OCR routes."""
    result = {}
    for document in baseline:
        doc_id = document["doc_id"]
        tier = document.get("extraction_fallback_backend")
        flags = sum(
            row["score"] < threshold
            for row in rows
            if row["doc_id"] == doc_id and row["tier"] == tier
        )
        prior = bool(document["ocr_required"])
        routed = prior or flags / document["page_count"] >= 0.10
        result[doc_id] = {
            "pages": document["page_count"],
            "rescued_tier": tier,
            "flagged_rescue_pages": flags,
            "prior_routed": prior,
            "routed": routed,
            "frozen_document_label": labels[doc_id]["label"],
            "newly_routed_usable": routed and not prior and labels[doc_id]["label"] == "usable",
        }
    return result


def gates(routing: dict, rate: float) -> dict[str, bool]:
    """Check both motivating documents, new usable routes, and the page ceiling."""
    return {
        "G1": all(routing[doc_id]["routed"] for doc_id in ("rf06", "rf07")),
        "G2": not any(row["newly_routed_usable"] for row in routing.values()),
        "G3": rate <= 0.02,
    }


def candidate_summary(rows: list[dict], baseline: list[dict], labels: dict, costs: dict) -> dict:
    """Report both operating points and tiers with document-cluster intervals."""
    primary = [row for row in rows if row["tier"] == "liteparse"]
    threshold = equal_cost_threshold(primary)
    result = {"equal_cost_threshold": threshold, "operating_points": {}}
    documents = [row["doc_id"] for row in baseline]
    for name, cutoff in (("as_designed", 0.50), ("equal_cost", threshold)):
        routing = simulate_routing(rows, baseline, labels, cutoff)
        populations = {}
        for tier in ("liteparse", "pypdf"):
            population = [row for row in rows if row["tier"] == tier]
            measured = metrics(population, cutoff)
            measured["document_cluster_interval"] = bootstrap_interval(
                population, cutoff, documents
            )
            measured["per_document"] = {
                doc_id: metrics([row for row in population if row["doc_id"] == doc_id], cutoff)
                for doc_id in documents
            }
            populations[tier] = measured
        primary_metrics = populations["liteparse"]
        new_usable = [doc_id for doc_id, row in routing.items() if row["newly_routed_usable"]]
        wasted_pages = sum(routing[doc_id]["pages"] for doc_id in new_usable)
        result["operating_points"][name] = {
            "threshold": cutoff,
            "populations": populations,
            "routing": routing,
            "gates": gates(routing, primary_metrics["healthy_false_positive_rate"]),
            "newly_routed_usable": new_usable,
            "projected_wasted_ocr": {
                "whole_document_pages": wasted_pages,
                "dots_mocr_seconds": wasted_pages * costs["dots_mocr_s_per_page"],
                "paddleocr_vl_seconds_range": [
                    wasted_pages * x for x in costs["paddleocr_vl_s_per_page"]
                ],
                "pooled_false_positive_pages": primary_metrics["healthy_false_positives"],
            },
        }
    cpu = [row["cpu_seconds"] for row in rows]
    wall = [row["wall_seconds"] for row in rows]
    result["timing"] = {
        "pages_and_tiers": len(rows),
        "cpu_seconds": sum(cpu),
        "wall_seconds": sum(wall),
        "cpu_seconds_per_page": float(np.mean(cpu)),
        "wall_seconds_per_page": float(np.mean(wall)),
    }
    return result


def attach_followup(summary: dict, payload: dict, digest: str) -> None:
    """Attach saved local-text results without choosing another threshold."""
    from score_local_text import followup_metrics, frozen_thresholds

    if payload["thresholds"] != frozen_thresholds(summary):
        raise ValueError("follow-up threshold differs from the frozen main verdict")
    gated = [row for row in payload["rows"] if row["population"] == "gated"]
    summary["local_text_followup"] = {
        "pages": len(payload["rows"]),
        "gated_pages": len(gated),
        "io06_pages": sum(row["doc_id"] == "io06" for row in gated),
        "signals": followup_metrics(payload),
    }
    summary["artefact_sha256"]["local_text_signal.json"] = digest


def run(source: Path) -> None:
    """Require complete paired scores, then save the main G1 to G3 verdict."""
    plan = approved_plan()
    verify_freeze(source)
    rescue = read_json(OUTPUT / "rescue_text.json")
    labels = read_json(source / "labels.json")["documents"]
    baseline = read_json(source / "output" / "arm_sampled_baseline" / "routing.json")["rows"]
    if len(baseline) != 40 or len({row["doc_id"] for row in baseline}) != 40:
        raise ValueError("document routing must cover all 40 frozen documents")
    candidates = {name: read_json(OUTPUT / f"candidate_{name.lower()}.json") for name in ("A", "B")}
    expected = eligible_rows(rescue["rows"])
    for payload in candidates.values():
        if len(payload["completed_documents"]) != 40:
            raise ValueError("candidate scoring is incomplete")
        verify_coverage(expected, payload["rows"])
        if any(
            not np.isfinite(row["score"]) or not 0 <= row["score"] <= 1 for row in payload["rows"]
        ):
            raise ValueError("candidate score is outside probability bounds")
    results = {
        name: candidate_summary(payload["rows"], baseline, labels, plan["false_positive_cost"])
        for name, payload in candidates.items()
    }
    primary = {
        name: [row for row in payload["rows"] if row["tier"] == "liteparse"]
        for name, payload in candidates.items()
    }
    paired = mcnemar(
        primary["A"],
        primary["B"],
        results["A"]["equal_cost_threshold"],
        results["B"]["equal_cost_threshold"],
    )
    measured = {
        name: result["operating_points"]["equal_cost"]["populations"]["liteparse"]
        for name, result in results.items()
    }
    delta = (measured["B"]["junk_flagged"] - measured["A"]["junk_flagged"]) / measured["A"][
        "junk_pages"
    ]
    passes = {
        name: all(result["operating_points"]["equal_cost"]["gates"].values())
        for name, result in results.items()
    }
    parity = read_json(OUTPUT / "parity.json")
    if not parity["passed"]:
        raise ValueError("P0 must pass before candidate B can be compared")
    verdict = recommend(passes["A"], passes["B"], delta, paired["p_one_sided"])
    summary = {
        "experiment": plan["experiment_id"],
        "recommendation": verdict,
        "status": "PASS" if verdict else "FAIL",
        "candidates": results,
        "adoption": {
            "margin": 0.10,
            "observed_delta": delta,
            "mcnemar": paired,
            "b_beats_a_by_margin_and_significance": delta >= 0.10 and paired["p_one_sided"] < 0.05,
        },
        "classes": {
            tier: dict(Counter(row["class"] for row in rescue["rows"] if row["tier"] == tier))
            for tier in ("liteparse", "pypdf")
        },
        "parity": {key: value for key, value in parity.items() if key != "rows"},
        "artefact_sha256": {
            name: sha256(OUTPUT / name)
            for name in (
                "rescue_text.json",
                "candidate_a.json",
                "candidate_b.json",
                "parity.json",
                "recall_check.json",
            )
        },
        "equal_cost_note": "Strict thresholds preserve ties; finite counts can give a rate below 0.02. Secondary pypdf uses the LiteParse threshold.",
    }
    local = OUTPUT / "local_text_signal.json"
    if local.exists():
        attach_followup(summary, read_json(local), sha256(local))
    atomic_json(OUTPUT / "summary.json", summary)
    print(f"[summary] {summary['status']}: recommend {verdict or 'neither'}", flush=True)
    for name, result in results.items():
        equal = result["operating_points"]["equal_cost"]
        print(
            f"[summary {name}] {equal['populations']['liteparse']} gates={equal['gates']}",
            flush=True,
        )


def main() -> None:
    """Read the source location from a runtime argument."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-exp", required=True, type=Path)
    args = parser.parse_args()
    run(args.source_exp.resolve())


if __name__ == "__main__":
    main()
