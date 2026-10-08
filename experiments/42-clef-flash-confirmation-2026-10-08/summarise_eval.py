"""Tasks 6.1 and 6.2: design D8 metrics, D5 gates and the D10 verdict under OD1.

Imports from Experiment 38 (unchanged): ``signal_stats.metrics``, ``mcnemar``,
``auc_badness`` and ``summarise_eval.simulate_routing``. Thresholds are the frozen
plan.json values; nothing is refitted.

    uv run --no-sync python summarise_eval.py
"""

from __future__ import annotations

import math
from collections import Counter

import numpy as np
from exp42_io import EXP38, OUTPUT, atomic_json, load_module, plan, read_json, sha256

STATS = load_module(EXP38 / "signal_stats.py", "exp38_signal_stats")
MARGIN, ALPHA, CEILING, FRACTION = 0.10, 0.05, 0.02, 0.10
DOTS_S_PER_PAGE = 38.2


def wilson(k: int, n: int, z: float = 1.959964) -> dict:
    """Wilson 95% score interval for k successes in n trials."""
    if not n:
        return {"lower": None, "upper": None}
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return {"lower": centre - half, "upper": centre + half}


def cluster_bootstrap(rows: list[dict], threshold: float, cls: str, seed: int = 42) -> dict:
    """Document-cluster bootstrap (2,000 resamples) of the flag rate in one class."""
    documents = sorted({r["doc_id"] for r in rows})
    total = Counter(r["doc_id"] for r in rows if r["class"] == cls)
    hit = Counter(r["doc_id"] for r in rows if r["class"] == cls and r["score"] < threshold)
    picks = np.random.default_rng(seed).integers(0, len(documents), (2000, len(documents)))
    den = np.array([total[d] for d in documents])[picks].sum(axis=1)
    num = np.array([hit[d] for d in documents])[picks].sum(axis=1)
    values = num[den > 0] / den[den > 0]
    return {
        "lower": float(np.quantile(values, 0.025)) if len(values) else None,
        "upper": float(np.quantile(values, 0.975)) if len(values) else None,
        "resamples": 2000,
        "seed": seed,
    }


def gates(routing: dict, junk_layer_docs: list[str], fp_rate: float) -> dict[str, bool]:
    """Design D5: G1 junk-layer documents route; G2 no usable newly routes; G3 ceiling."""
    return {
        "G1": all(routing[d]["routed"] for d in junk_layer_docs),
        "G2": not any(r["newly_routed_usable"] for r in routing.values()),
        "G3": fp_rate <= CEILING,
    }


def margin(clef: dict, a: dict, paired: dict) -> dict:
    """Adoption margin: recall difference at least 0.10 and McNemar p below 0.05."""
    delta = clef["junk_recall"] - a["junk_recall"]
    return {
        "delta": delta,
        "p_one_sided": paired["p_one_sided"],
        "pass": delta >= MARGIN and paired["p_one_sided"] < ALPHA,
    }


def primary_pass(gate: dict[str, bool], option: str, margin_pass: bool | None) -> bool:
    """OD1: option A needs G1, G2 (and the margin); option B adds G3."""
    needed = ["G1", "G2"] + (["G3"] if option == "B" else [])
    return all(gate[g] for g in needed) and (margin_pass is None or margin_pass)


def verdict(clef_passes: bool, a_passes: bool) -> str:
    """Design D10 outcome mapping."""
    if clef_passes:
        return "PASS"
    return "FAIL for Clef-flash" if a_passes else "FAIL"


def arm_summary(rows, threshold, baseline, labels, junk_docs) -> dict:
    """Metrics, intervals, routing and gates for one arm at its frozen threshold."""
    simulate = load_module(EXP38 / "summarise_eval.py", "exp38_summarise_eval").simulate_routing
    out = {"threshold": threshold, "populations": {}}
    for tier in ("liteparse", "pypdf"):
        population = [r for r in rows if r["tier"] == tier]
        measured = STATS.metrics(population, threshold)
        measured["junk_recall_wilson"] = wilson(measured["junk_flagged"], measured["junk_pages"])
        measured["fp_rate_wilson"] = wilson(
            measured["healthy_false_positives"], measured["healthy_pages"]
        )
        measured["junk_recall_cluster"] = cluster_bootstrap(population, threshold, "junk")
        measured["fp_rate_cluster"] = cluster_bootstrap(population, threshold, "healthy")
        measured["auc"] = STATS.auc_badness(population)
        measured["per_document"] = {
            d: STATS.metrics([r for r in population if r["doc_id"] == d], threshold)
            for d in sorted({r["doc_id"] for r in population})
        }
        measured["sensitivity_fp_rate"] = {
            f"x{f}": STATS.metrics(population, threshold * f)["healthy_false_positive_rate"]
            for f in (0.9, 1.1)
        }
        out["populations"][tier] = measured
    routing = simulate(rows, baseline, labels, threshold)
    for doc_id, row in routing.items():
        row["junk_text_layer"] = doc_id in junk_docs
        row["projected_ocr_seconds"] = (
            row["pages"] * DOTS_S_PER_PAGE if row["routed"] and not row["prior_routed"] else 0.0
        )
    out["routing"] = routing
    out["gates"] = gates(
        routing, junk_docs, out["populations"]["liteparse"]["healthy_false_positive_rate"]
    )
    out["missed_junk_layer_documents"] = [d for d in junk_docs if not routing[d]["routed"]]
    out["newly_routed_usable"] = [d for d, r in routing.items() if r["newly_routed_usable"]]
    return out


def main() -> None:
    """Write output/summary.json."""
    current = plan()
    option = current["gates"]["priority"]
    hashes = read_json(OUTPUT / "output_hashes.json")["files"]
    for name, digest in hashes.items():
        if sha256(OUTPUT / name) != digest:
            raise SystemExit(f"{name} changed after hashing")
    labels = read_json(OUTPUT / "labels.json")["documents"]
    baseline = read_json(OUTPUT / "control_routing.json")["rows"]
    junk_docs = sorted(d for d, v in labels.items() if v["junk_text_layer"])
    rows = {
        "A": read_json(OUTPUT / "candidate_a.json")["rows"],
        "clef": read_json(OUTPUT / "clef_flash.json")["rows"],
    }
    thresholds = {
        "A": current["thresholds"]["word_check_a"]["value"],
        "clef": current["thresholds"]["clef_flash_q8_0_w1"]["value"],
    }
    arms = {k: arm_summary(rows[k], thresholds[k], baseline, labels, junk_docs) for k in rows}
    control = arm_summary(
        [{**r, "score": 1.0} for r in rows["A"]], 0.0, baseline, labels, junk_docs
    )
    lite = {k: [r for r in v if r["tier"] == "liteparse"] for k, v in rows.items()}
    paired = STATS.mcnemar(lite["A"], lite["clef"], thresholds["A"], thresholds["clef"])
    adopt = margin(
        arms["clef"]["populations"]["liteparse"], arms["A"]["populations"]["liteparse"], paired
    )
    clef_passes = primary_pass(arms["clef"]["gates"], option, adopt["pass"])
    a_passes = primary_pass(arms["A"]["gates"], option, None)
    atomic_json(
        OUTPUT / "summary.json",
        {
            "experiment": current["experiment_id"],
            "gate_priority": option,
            "verdict": verdict(clef_passes, a_passes),
            "clef_flash_passes_primary_gates_and_margin": clef_passes,
            "a_passes_primary_gates": a_passes,
            "adoption": {"mcnemar": paired, **adopt},
            "junk_text_layer_documents": junk_docs,
            "arms": {"control": control, **arms},
            "output_sha256": hashes,
        },
    )
    print("summary written", flush=True)


if __name__ == "__main__":
    main()
