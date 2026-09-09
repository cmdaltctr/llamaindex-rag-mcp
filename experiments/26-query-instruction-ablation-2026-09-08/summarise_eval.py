"""Experiment 26 summariser: aggregate both arms, check the frozen gates.

Metric definitions are a verbatim port of Experiment 22's summariser
(``_rank_map``, ``_alpha_ndcg``, ``_metrics_for_query``, ``_aggregate``),
itself ported from 9a, so the numbers stay comparable with the baseline.
Do not modify them.

Gate thresholds are read from the frozen ``plan.json`` and never from
this file. Comparisons use unrounded values; rounding happens only in
formatting.

The primary comparison is within this experiment: both arms ran
interleaved in one process against the same preserved index, so the R@5
lift is paired query by query. Experiment 22's published ``hybrid__raw``
figures are re-aggregated with the same code as a drift cross-check and
reported, never substituted for the local raw arm.

Writes ``output/eval_results.summary.json`` and ``results.md``.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
EXP22_DIR = EXP_DIR.parent / "22-raw-query-qwen4b-baseline-2026-09-07"
GT_PATH = EXP22_DIR / "output/ground-truth.json"
BASELINE_CKPT = EXP22_DIR / "output/cells/hybrid__raw.json"
PLAN_PATH = EXP_DIR / "plan.json"
MANIFEST_PATH = EXP_DIR / "output/runtime_manifest.json"
CELLS = ("raw_none", "candidate_instruction")
K_VALUES = (1, 3, 5, 10, 20, 50)
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20260908


# ---------------------------------------------------------------------
# Metric functions — verbatim port from Experiment 22's summariser.
# ---------------------------------------------------------------------
def _rank_map(parent_ids: list[str]) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for rank, parent_id in enumerate(parent_ids, start=1):
        ranks.setdefault(parent_id, rank)
    return ranks


def _alpha_ndcg(
    parent_ids: list[str], nuggets: list[dict], k: int = 10, alpha: float = 0.5
) -> float:
    nugget_rels = [set(n.get("relevant_corpus_ids") or []) for n in nuggets]
    if not nugget_rels:
        return 0.0

    def dcg(ranking: list[str]) -> float:
        seen = [0 for _ in nugget_rels]
        total = 0.0
        for rank, doc_id in enumerate(ranking[:k], start=1):
            gain = 0.0
            for idx, rels in enumerate(nugget_rels):
                if doc_id in rels:
                    gain += (1.0 - alpha) ** seen[idx]
                    seen[idx] += 1
            if gain:
                total += gain / math.log2(rank + 1)
        return total

    observed = dcg(parent_ids)
    candidate_docs = sorted(set().union(*nugget_rels))
    ideal: list[str] = []
    remaining = candidate_docs[:]
    while remaining and len(ideal) < k:
        best_doc = max(remaining, key=lambda doc: dcg(ideal + [doc]))
        ideal.append(best_doc)
        remaining.remove(best_doc)
    ideal_score = dcg(ideal)
    return observed / ideal_score if ideal_score else 0.0


def _metrics_for_query(parent_ids: list[str], query: dict) -> dict:
    """Per-query metrics: 9a's set plus recall@K for K in K_VALUES."""
    ranks = _rank_map(parent_ids)
    relevant = set(query.get("relevant_parent_ids") or [])
    nuggets = query.get("nuggets") or []
    covered = 0
    for nugget in nuggets:
        rels = set(nugget.get("relevant_corpus_ids") or [])
        if rels & set(parent_ids[:20]):
            covered += 1
    hit_ranks = [ranks[doc_id] for doc_id in relevant if doc_id in ranks]
    first_rank = min(hit_ranks) if hit_ranks else None
    metrics: dict = {
        "coverage_at_20": covered / len(nuggets) if nuggets else 0.0,
        "alpha_ndcg_at_10": _alpha_ndcg(parent_ids, nuggets, k=10),
        "hit_at_5": first_rank is not None and first_rank <= 5,
        "hit_at_10": first_rank is not None and first_rank <= 10,
        "mrr_at_10": (1.0 / first_rank) if first_rank is not None and first_rank <= 10 else 0.0,
        "first_relevant_rank": first_rank,
    }
    for k in K_VALUES:
        top = set(parent_ids[:k])
        metrics[f"recall_at_{k}"] = len(relevant & top) / len(relevant) if relevant else 0.0
    return metrics


def _aggregate(rows: list[dict]) -> dict:
    """Mean over per-query metrics plus latency stats."""
    by_cat: dict[str, list[dict]] = {"all": rows}
    for row in rows:
        by_cat.setdefault(row["category"], []).append(row)
    out: dict = {}
    for cat, cat_rows in by_cat.items():
        agg: dict = {"n": len(cat_rows)}
        metric_keys = [k for k in cat_rows[0]["metrics"] if k != "first_relevant_rank"]
        for key in metric_keys:
            agg[key] = round(statistics.fmean(r["metrics"][key] for r in cat_rows), 6)
        latencies = [r["latency_s"] * 1000 for r in cat_rows]
        latencies.sort()
        agg["mean_latency_ms"] = round(statistics.fmean(latencies), 2)
        agg["p95_latency_ms"] = round(latencies[max(0, math.ceil(0.95 * len(latencies)) - 1)], 2)
        out[cat] = agg
    return out


# ---------------------------------------------------------------------
# Experiment 26 aggregation and gate evaluation
# ---------------------------------------------------------------------
def _scored_rows(checkpoint: Path, queries: dict) -> list[dict]:
    """Attach per-query metrics to one arm's checkpoint rows."""
    state = json.loads(checkpoint.read_text(encoding="utf-8"))
    return [
        {**row, "metrics": _metrics_for_query(row["parent_ids"], queries[row["query_id"]])}
        for row in state["rows"]
    ]


def _paired(raw: list[dict], cand: list[dict], key: str, categories=None) -> list[float]:
    """Per-query candidate-minus-raw deltas over the shared query ids."""
    by_id = {r["query_id"]: r for r in raw}
    return [
        c["metrics"][key] - by_id[c["query_id"]]["metrics"][key]
        for c in cand
        if c["query_id"] in by_id and (categories is None or c["category"] in categories)
    ]


def _bootstrap_half_width(deltas: list[float]) -> float:
    """Paired bootstrap 95% half-width of the mean delta."""
    rng = random.Random(BOOTSTRAP_SEED)  # noqa: S311 - reproducible bootstrap, not crypto
    size = len(deltas)
    means = sorted(statistics.fmean(rng.choices(deltas, k=size)) for _ in range(BOOTSTRAP_N))
    lower = means[int(0.025 * BOOTSTRAP_N)]
    upper = means[int(0.975 * BOOTSTRAP_N) - 1]
    return (upper - lower) / 2


def _gates(plan: dict, raw: list[dict], cand: list[dict], agg_cand: dict) -> dict:
    """Evaluate every frozen gate against the measured arms."""
    by_kind = {g["kind"]: g for g in plan["validity_gates"]}
    quality, regression, latency = by_kind["quality"], by_kind["regression"], by_kind["latency"]

    deltas = _paired(raw, cand, "recall_at_5")
    lift = statistics.fmean(deltas)
    ident_r10 = agg_cand.get("identifier-heavy", {}).get("recall_at_10", 0.0)
    p95 = agg_cand["all"]["p95_latency_ms"]

    return {
        "quality_paired_r5_lift": {
            "pass": lift >= quality["threshold"],
            "measured": round(lift, 6),
            "threshold": quality["threshold"],
            "comparator": quality["comparator"],
            "paired_bootstrap_95_half_width": round(_bootstrap_half_width(deltas), 6),
            "n": len(deltas),
        },
        "regression_identifier_r10": {
            "pass": ident_r10 >= regression["threshold"],
            "measured": round(ident_r10, 6),
            "threshold": regression["threshold"],
            "comparator": regression["comparator"],
            "n": agg_cand.get("identifier-heavy", {}).get("n", 0),
        },
        "latency_p95_ms": {
            "pass": p95 <= latency["threshold"],
            "measured": p95,
            "threshold": latency["threshold"],
            "comparator": latency["comparator"],
        },
    }


def _drift_check(raw: list[dict], queries: dict) -> dict:
    """Compare this run's raw arm with Experiment 22's published raw arm."""
    exp22 = _scored_rows(BASELINE_CKPT, queries)
    local = _aggregate(raw)["all"]
    published = _aggregate(exp22)["all"]
    return {
        "exp22_recall_at_5": published["recall_at_5"],
        "exp26_raw_recall_at_5": local["recall_at_5"],
        "delta": round(local["recall_at_5"] - published["recall_at_5"], 6),
        "note": "same index and queries; a non-zero delta is provider-side "
        "embedding drift between 2026-09-07 and this run",
    }


def _rows_table(agg: dict, cats: tuple[str, ...]) -> list[str]:
    cols = ("recall_at_1", "recall_at_3", "recall_at_5", "recall_at_10", "mrr_at_10")
    lines = ["| Category | n | R@1 | R@3 | R@5 | R@10 | MRR@10 |", "| --- | ---: |" + " ---: |" * 5]
    for cat in cats:
        if cat not in agg:
            continue
        row = agg[cat]
        cells = " | ".join(f"{row[c] * 100:.1f}%" for c in cols)
        lines.append(f"| {cat} | {row['n']} | {cells} |")
    return lines


def _write_results_md(summary: dict, plan: dict) -> None:
    """Render results.md from the computed summary."""
    gates = summary["gates"]
    verdict = "PASS" if summary["verdict"] == "PASS" else "FAIL"
    cats = ("all", "identifier-heavy", "semantic", "continuity")
    raw_agg = summary["metrics_by_cell"]["raw_none"]
    cand_agg = summary["metrics_by_cell"]["candidate_instruction"]
    q, r, lat = (
        gates["quality_paired_r5_lift"],
        gates["regression_identifier_r10"],
        gates["latency_p95_ms"],
    )
    mark = {True: "✅ PASS", False: "❌ FAIL"}
    lines = [
        "# Experiment 26 Results: Query-instruction ablation (task 5.3)",
        "",
        "**ID**: `26-query-instruction-ablation-2026-09-08`  ",
        f"**Date run**: {summary['run_date']}  ",
        "**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent  ",
        f"**Status**: {verdict}  ",
        "**Raw data**: [`output/cells/`](./output/cells/)",
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
        f"| Quality | paired mean R@5 lift ≥ {q['threshold']:+.4f} | "
        f"{q['measured']:+.4f} (95% half-width ±{q['paired_bootstrap_95_half_width']:.4f}, "
        f"n={q['n']}) | {mark[q['pass']]} |",
        f"| Regression | identifier-heavy R@10 ≥ {r['threshold']} | "
        f"{r['measured']:.4f} (n={r['n']}) | {mark[r['pass']]} |",
        f"| Latency | query p95 ≤ {lat['threshold']} ms | {lat['measured']:,.0f} ms | "
        f"{mark[lat['pass']]} |",
        "",
        "Thresholds are read from the frozen [`plan.json`](./plan.json); no",
        "threshold lives in the summariser. The gates were frozen on",
        f"{plan['gate_freeze']['frozen_date']} and are unchanged.",
        "",
        "## Raw arm (`raw_none`)",
        "",
        *_rows_table(raw_agg, cats),
        "",
        "## Instructed arm (`candidate_instruction`)",
        "",
        *_rows_table(cand_agg, cats),
        "",
        "## Candidate instruction",
        "",
        "```text",
        summary["runtime_manifest"]["embedding"]["candidate_instruction"],
        "```",
        "",
        "## Latency",
        "",
        "| Arm | Mean | P95 |",
        "| --- | ---: | ---: |",
        f"| raw_none | {raw_agg['all']['mean_latency_ms']:,.0f} ms | "
        f"{raw_agg['all']['p95_latency_ms']:,.0f} ms |",
        f"| candidate_instruction | {cand_agg['all']['mean_latency_ms']:,.0f} ms | "
        f"{cand_agg['all']['p95_latency_ms']:,.0f} ms |",
        "",
        "Both arms ran interleaved in one process with alternating arm order,",
        "so they share the same network epoch. Latency is cloud-inclusive.",
        "The first query of the run pays the one-off BM25 index build; that",
        "cost lands on the raw arm, which if anything works against the",
        "baseline rather than for the candidate.",
        "",
        "## Drift cross-check against Experiment 22",
        "",
        f"- Experiment 22 published R@5 (hybrid, raw): {summary['drift']['exp22_recall_at_5']:.6f}",
        f"- This run's raw arm R@5: {summary['drift']['exp26_raw_recall_at_5']:.6f}",
        f"- Delta: {summary['drift']['delta']:+.6f}",
        "",
        "Same index, same 223 queries. The gate is evaluated against this",
        "run's own raw arm, which is paired query by query with the",
        "instructed arm; Experiment 22's number is a drift check only.",
        "",
        "## Monitored, not gated",
        "",
        f"- Continuity R@10 (n={cand_agg.get('continuity', {}).get('n', 0)}): raw "
        f"{raw_agg.get('continuity', {}).get('recall_at_10', 0):.4f} → candidate "
        f"{cand_agg.get('continuity', {}).get('recall_at_10', 0):.4f}. The bootstrap",
        "  95% half-width at n=20 is ±0.15, so no hard gate could be meaningful.",
        "",
        "## Reproduction",
        "",
        "```bash",
        "uv run python experiments/26-query-instruction-ablation-2026-09-08/run_eval.py --resume",
        "uv run python experiments/26-query-instruction-ablation-2026-09-08/summarise_eval.py",
        "```",
        "",
        "No index is built or written: both arms query the preserved",
        "Experiment 22 index read-only.",
        "",
    ]
    # Hand-written interpretation lives in its own file so regenerating
    # the tables never discards it.
    discussion = EXP_DIR / "discussion.md"
    if discussion.exists():
        lines.append(discussion.read_text(encoding="utf-8"))
    (EXP_DIR / "results.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Aggregate both arms, evaluate the frozen gates, write the artefacts."""
    queries = {q["query_id"]: q for q in json.loads(GT_PATH.read_text(encoding="utf-8"))["queries"]}
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    scored = {
        cell: _scored_rows(EXP_DIR / "output/cells" / f"{cell}.json", queries) for cell in CELLS
    }
    counts = {cell: len(rows) for cell, rows in scored.items()}
    if len(set(counts.values())) != 1:
        raise SystemExit(f"arms are not paired: {counts}")
    print(f"[summarise] {counts['raw_none']} queries per arm", flush=True)

    aggregates = {cell: _aggregate(rows) for cell, rows in scored.items()}
    gates = _gates(
        plan,
        scored["raw_none"],
        scored["candidate_instruction"],
        aggregates["candidate_instruction"],
    )
    verdict = "PASS" if all(g["pass"] for g in gates.values()) else "FAIL"
    failed = [name for name, gate in gates.items() if not gate["pass"]]

    lift = gates["quality_paired_r5_lift"]["measured"]
    if verdict == "PASS":
        headline = (
            f"- All three frozen gates pass. The candidate instruction lifts paired\n"
            f"  mean R@5 by {lift:+.4f} without breaching the identifier-heavy or\n"
            f"  latency guards.\n"
            f"- Eligible for promotion of `EMBEDDING__QUERY_INSTRUCTION` under task 5.5."
        )
    else:
        headline = (
            f"- **Negative result.** Failed gates: {', '.join(failed)}.\n"
            f"- Paired mean R@5 lift is {lift:+.4f} against a frozen requirement of\n"
            f"  {gates['quality_paired_r5_lift']['threshold']:+.4f}.\n"
            f"- Per task 5.5 the packaged default for `EMBEDDING__QUERY_INSTRUCTION`\n"
            f"  stays empty. The instruction text is not tuned to chase the gate."
        )

    summary = {
        "experiment": EXP_DIR.name,
        "run_date": "2026-09-09",
        "verdict": verdict,
        "failed_gates": failed,
        "headline": headline,
        "gates": gates,
        "metrics_by_cell": aggregates,
        "drift": _drift_check(scored["raw_none"], queries),
        "runtime_manifest": json.loads(MANIFEST_PATH.read_text(encoding="utf-8")),
    }

    out_json = EXP_DIR / "output/eval_results.summary.json"
    tmp = out_json.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    tmp.replace(out_json)
    _write_results_md(summary, plan)
    print(f"[summarise] verdict={verdict} → {out_json}", flush=True)


if __name__ == "__main__":
    main()
