"""Summarise every candidate at leave-one-document-out thresholds (amendment A3).

Base candidates A, B, B2 and C use held-out equal-cost thresholds. B_sel and
C_sel pick a pre-registered wording per held-out document (nested selection).
D is the A-then-Jev cascade. All share the same gates and adoption rule.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from experiment_io import OUTPUT, approved_plan, atomic_json, read_json, sha256, verify_freeze
from lodo import cascade_select, held_out, lodo_thresholds, nested_select
from score_signals import eligible_rows, verify_coverage
from signal_stats import bootstrap_interval, mcnemar, metrics
from summarise_eval import gates, simulate_routing

BASE = ("A", "B", "B2", "C")
WORDING_FILES = {"B_sel": ("julia", "B2"), "C_sel": ("jev", "C"), "E_sel": ("openjev", "E")}


def evaluate(shifted: list[dict], baseline: list[dict], labels: dict) -> dict:
    """Report held-out flags per tier, routing and gates at the shared cut-off 0."""
    documents = [row["doc_id"] for row in baseline]
    routing = simulate_routing(shifted, baseline, labels, 0.0)
    populations = {}
    for tier in ("liteparse", "pypdf"):
        population = [row for row in shifted if row["tier"] == tier]
        measured = metrics(population, 0.0)
        measured.pop("threshold")
        measured["document_cluster_interval"] = bootstrap_interval(population, 0.0, documents)
        populations[tier] = measured
    rate = populations["liteparse"]["healthy_false_positive_rate"]
    return {
        "populations": populations,
        "routing": routing,
        "gates": gates(routing, rate),
        "newly_routed_usable": [d for d, row in routing.items() if row["newly_routed_usable"]],
    }


def adoption(results: dict, shifted: dict) -> dict:
    """Apply the 0.10 margin and one-sided McNemar test of each model against A."""
    primary = {
        name: [r for r in rows if r["tier"] == "liteparse"] for name, rows in shifted.items()
    }
    junk = results["A"]["populations"]["liteparse"]["junk_pages"]
    caught = {n: results[n]["populations"]["liteparse"]["junk_flagged"] for n in results}
    passes = {n: all(results[n]["gates"].values()) for n in results}
    out: dict[str, Any] = {"passes_gates": passes}
    models = [name for name in results if name != "A"]
    for name in models:
        test = mcnemar(primary["A"], primary[name], 0.0, 0.0)
        delta = (caught[name] - caught["A"]) / junk
        out[name] = {
            "delta_vs_a": delta,
            "mcnemar_vs_a": test,
            "adopt": passes[name] and delta >= 0.10 and test["p_one_sided"] < 0.05,
        }
    adopted = [n for n in models if out[n]["adopt"]]
    out["recommendation"] = adopted or (["A"] if passes["A"] else [])
    return out


def load_wordings(model: str, w1: list[dict]) -> dict[str, list[dict]] | None:
    """Return W1 to W3 rows for one model, or None until both new wordings are scored."""
    paths = {w: OUTPUT / f"wording_{model}_{w.lower()}.json" for w in ("W2", "W3")}
    if not all(path.exists() for path in paths.values()):
        return None
    return {"W1": w1, **{w: read_json(path)["rows"] for w, path in paths.items()}}


def run(source: Path) -> None:
    """Require complete scores, then save the held-out verdict for every candidate."""
    plan = approved_plan()
    verify_freeze(source)
    rescue = read_json(OUTPUT / "rescue_text.json")
    labels = read_json(source / "labels.json")["documents"]
    baseline = read_json(source / "output" / "arm_sampled_baseline" / "routing.json")["rows"]
    if len(baseline) != 40:
        raise ValueError("document routing must cover all 40 frozen documents")
    expected = eligible_rows(rescue["rows"])
    rows = {n: read_json(OUTPUT / f"candidate_{n.lower()}.json")["rows"] for n in BASE}
    shifted = {n: held_out(rows[n], lodo_thresholds(rows[n])) for n in BASE}
    extra: dict[str, Any] = {"thresholds": {n: lodo_thresholds(rows[n]) for n in BASE}}
    openjev_w1 = OUTPUT / "wording_openjev_w1.json"
    if openjev_w1.exists():
        rows["E"] = read_json(openjev_w1)["rows"]
        shifted["E"] = held_out(rows["E"], lodo_thresholds(rows["E"]))
    for name, (model, w1) in WORDING_FILES.items():
        if w1 not in rows:
            continue
        variants = load_wordings(model, rows[w1])
        if variants is None:
            continue
        shifted[name], chosen = nested_select(variants)
        extra[f"{name}_chosen"] = dict(Counter(chosen.values()))
        extra[f"{name}_by_document"] = chosen
    shifted["D"], sent = cascade_select(
        rows["A"], rows["C"], plan["candidates"]["D"]["primary_screen_rate"]
    )
    extra["D_share_sent_to_jev"] = sent
    shifted["D_julia"], _ = cascade_select(
        rows["A"], rows["B2"], plan["candidates"]["D"]["primary_screen_rate"]
    )
    if "E" in rows:
        shifted["D_openjev"], extra["D_openjev_share_sent"] = cascade_select(
            rows["A"], rows["E"], plan["candidates"]["D"]["primary_screen_rate"]
        )
    for payload in shifted.values():
        verify_coverage(expected, payload)
    results = {n: evaluate(shifted[n], baseline, labels) for n in shifted}
    sensitivity = {}
    for rate in plan["candidates"]["D"]["sensitivity_screen_rates"]:
        cascade, share = cascade_select(rows["A"], rows["C"], rate)
        sensitivity[str(rate)] = {**evaluate(cascade, baseline, labels), "share_sent_to_jev": share}
        julia, _ = cascade_select(rows["A"], rows["B2"], rate)
        sensitivity[f"julia_{rate}"] = evaluate(julia, baseline, labels)
        if "E" in rows:
            local, _ = cascade_select(rows["A"], rows["E"], rate)
            sensitivity[f"openjev_{rate}"] = evaluate(local, baseline, labels)
    verdict = adoption(results, shifted)
    summary = {
        "experiment": plan["experiment_id"],
        "amendment": "A3",
        "method": "leave-one-document-out equal-cost thresholds; strict flag score < threshold",
        "status": "PASS" if verdict["recommendation"] else "FAIL",
        "candidates": results,
        "adoption": verdict,
        "selection": extra,
        "d_sensitivity": sensitivity,
        "artefact_sha256": {
            path.name: sha256(path)
            for path in sorted(OUTPUT.glob("candidate_*.json"))
            + sorted(OUTPUT.glob("wording_*.json"))
        },
    }
    atomic_json(OUTPUT / "lodo_summary.json", summary)
    print(f"[lodo] {summary['status']}: {verdict['recommendation']}", flush=True)


def main() -> None:
    """Read source location argument."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-exp", required=True, type=Path)
    run(parser.parse_args().source_exp.resolve())


if __name__ == "__main__":
    main()
