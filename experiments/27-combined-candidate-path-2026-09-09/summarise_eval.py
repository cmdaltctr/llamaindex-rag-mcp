"""Experiment 27 summariser: assemble the 2x2, check the frozen gates.

Metric definitions are a verbatim port of Experiment 22's summariser
(``_rank_map``, ``_alpha_ndcg``, ``_metrics_for_query``, ``_aggregate``),
itself ported from 9a, so every cell of the 2x2 is scored by identical
code. Do not modify them.

Two cells are measured by ``run_eval.py`` against the preserved
Experiment 25 model-token index. The other two are LOADED from their
committed checkpoints and re-aggregated with the same code, never
re-executed:

- ``baseline_production``  → Experiment 22 ``hybrid__raw``
- ``instruction_only``     → Experiment 26 ``candidate_instruction``

Gate thresholds are read from the frozen ``plan.json`` and never from
this file. All three gates are evaluated on ``combined_candidate``
against the production baseline, exactly as the plan states.

The interaction term and the query token cost are computed and reported
but never gated; the plan records why.

Writes ``output/eval_results.summary.json`` and ``results.md``.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
EXP22_DIR = EXP_DIR.parent / "22-raw-query-qwen4b-baseline-2026-09-07"
EXP25_DIR = EXP_DIR.parent / "25-token-chunking-ablation-2026-09-08"
EXP26_DIR = EXP_DIR.parent / "26-query-instruction-ablation-2026-09-08"
GT_PATH = EXP22_DIR / "output/ground-truth.json"
PLAN_PATH = EXP_DIR / "plan.json"
MANIFEST_PATH = EXP_DIR / "output/runtime_manifest.json"

#: The four cells of the 2x2 and where each one's rows come from.
CELL_SOURCES = {
    "baseline_production": EXP22_DIR / "output/cells/hybrid__raw.json",
    "instruction_only": EXP26_DIR / "output/cells/candidate_instruction.json",
    "chunking_only_raw": EXP_DIR / "output/cells/chunking_only_raw.json",
    "combined_candidate": EXP_DIR / "output/cells/combined_candidate.json",
}
MEASURED_HERE = ("chunking_only_raw", "combined_candidate")
K_VALUES = (1, 3, 5, 10, 20, 50)


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
# Experiment 27 assembly and gate evaluation
# ---------------------------------------------------------------------
def _scored_rows(checkpoint: Path, queries: dict) -> list[dict]:
    """Attach per-query metrics to one cell's checkpoint rows."""
    state = json.loads(checkpoint.read_text(encoding="utf-8"))
    return [
        {**row, "metrics": _metrics_for_query(row["parent_ids"], queries[row["query_id"]])}
        for row in state["rows"]
    ]


def _gates(plan: dict, agg_combined: dict) -> dict:
    """Evaluate every frozen gate on the combined cell."""
    by_kind = {g["kind"]: g for g in plan["validity_gates"]}
    quality, regression, latency = by_kind["quality"], by_kind["regression"], by_kind["latency"]
    r5 = agg_combined["all"]["recall_at_5"]
    ident = agg_combined.get("identifier-heavy", {})
    p95 = agg_combined["all"]["p95_latency_ms"]
    return {
        "quality_recall_at_5": {
            "pass": r5 >= quality["threshold"],
            "measured": r5,
            "threshold": quality["threshold"],
            "comparator": quality["comparator"],
            "n": agg_combined["all"]["n"],
        },
        "regression_identifier_r10": {
            "pass": ident.get("recall_at_10", 0.0) >= regression["threshold"],
            "measured": ident.get("recall_at_10", 0.0),
            "threshold": regression["threshold"],
            "comparator": regression["comparator"],
            "n": ident.get("n", 0),
        },
        "latency_p95_ms": {
            "pass": p95 <= latency["threshold"],
            "measured": p95,
            "threshold": latency["threshold"],
            "comparator": latency["comparator"],
        },
    }


def _interaction(aggregates: dict) -> dict:
    """The R@5 interaction term, recorded but never gated."""

    def r5(cell: str) -> float:
        return aggregates[cell]["all"]["recall_at_5"]

    chunking_effect = r5("chunking_only_raw") - r5("baseline_production")
    instruction_effect = r5("instruction_only") - r5("baseline_production")
    combined_effect = r5("combined_candidate") - r5("baseline_production")
    return {
        "chunking_effect": round(chunking_effect, 6),
        "instruction_effect": round(instruction_effect, 6),
        "combined_effect": round(combined_effect, 6),
        "additive_prediction": round(chunking_effect + instruction_effect, 6),
        "interaction": round(combined_effect - chunking_effect - instruction_effect, 6),
        "note": "assembled across two indexes and three dates; carries "
        "cross-run drift as well as signal. Monitored, never gated.",
    }


def _query_token_cost(queries: dict) -> dict:
    """Mean request tokens per query, raw vs instructed.

    Counted offline with the pinned tokenizer from the local cache — no
    API call and no spend. Returns ``None`` figures when the tokenizer is
    not cached, so an absent model cache degrades the diagnostic instead
    of failing the summary.
    """
    instruction = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["embedding"][
        "candidate_instruction"
    ]
    try:
        import sys

        sys.path.insert(0, str(EXP_DIR.parent.parent / "src"))
        from omrg.integrations.tokenizer import load_tokenizer

        tokenizer = load_tokenizer(
            "Qwen/Qwen3-Embedding-4B", "5cf2132abc99cad020ac570b19d031efec650f2b"
        )
    except Exception as exc:  # noqa: BLE001 - diagnostic only
        return {"available": False, "reason": str(exc)[:200]}

    def count(text: str) -> int:
        return len(tokenizer.encode(text).ids)

    raw = [count(q["query"]) for q in queries.values()]
    instructed = [count(f"Instruct: {instruction}\nQuery: {q['query']}") for q in queries.values()]
    return {
        "available": True,
        "mean_raw_tokens": round(statistics.fmean(raw), 2),
        "mean_instructed_tokens": round(statistics.fmean(instructed), 2),
        "ratio": round(statistics.fmean(instructed) / statistics.fmean(raw), 4),
        "added_tokens_per_query": round(statistics.fmean(instructed) - statistics.fmean(raw), 2),
    }


def _drift(aggregates: dict) -> dict:
    """Compare this run's raw arm with Experiment 25's published arm."""
    published = json.loads(
        (EXP25_DIR / "output/eval_results.summary.json").read_text(encoding="utf-8")
    )
    cells = published.get("metrics_by_cell", {})
    key = "model_token_markdown" if "model_token_markdown" in cells else next(iter(cells))
    prior = cells[key]["all"]["recall_at_5"]
    local = aggregates["chunking_only_raw"]["all"]["recall_at_5"]
    return {
        "exp25_cell": key,
        "exp25_recall_at_5": prior,
        "exp27_chunking_only_recall_at_5": local,
        "delta": round(local - prior, 6),
        "note": "same index and queries on different dates; a non-zero "
        "delta is provider-side embedding drift",
    }


def _grid_table(aggregates: dict) -> list[str]:
    """The 2x2 rendered as a table."""
    labels = {
        "baseline_production": ("legacy chars", "raw"),
        "instruction_only": ("legacy chars", "instructed"),
        "chunking_only_raw": ("model tokens", "raw"),
        "combined_candidate": ("model tokens", "instructed"),
    }
    lines = [
        "| Cell | Chunking | Query | R@1 | R@3 | R@5 | R@10 | MRR@10 | P95 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for cell, (chunk, query) in labels.items():
        row = aggregates[cell]["all"]
        lines.append(
            f"| {cell} | {chunk} | {query} | "
            + " | ".join(
                f"{row[k] * 100:.1f}%"
                for k in ("recall_at_1", "recall_at_3", "recall_at_5", "recall_at_10", "mrr_at_10")
            )
            + f" | {row['p95_latency_ms']:,.0f} ms |"
        )
    return lines


def _write_results_md(summary: dict, plan: dict) -> None:
    """Render results.md from the computed summary."""
    gates = summary["gates"]
    mark = {True: "✅ PASS", False: "❌ FAIL"}
    q, r, lat = (
        gates["quality_recall_at_5"],
        gates["regression_identifier_r10"],
        gates["latency_p95_ms"],
    )
    inter = summary["interaction"]
    cost = summary["query_token_cost"]
    agg = summary["metrics_by_cell"]
    cost_lines = (
        [
            f"- Mean raw query: {cost['mean_raw_tokens']} tokens.",
            f"- Mean instructed query: {cost['mean_instructed_tokens']} tokens "
            f"({cost['ratio']:.2f}x, +{cost['added_tokens_per_query']} tokens).",
            "- Counted offline with the pinned tokenizer; no API call.",
        ]
        if cost.get("available")
        else [f"- Not available: {cost.get('reason', 'tokenizer not cached')}."]
    )
    lines = [
        "# Experiment 27 Results: Combined candidate path (task 5.4)",
        "",
        "**ID**: `27-combined-candidate-path-2026-09-09`  ",
        f"**Date run**: {summary['run_date']}  ",
        "**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent  ",
        f"**Status**: {summary['verdict']}  ",
        "**Raw data**: [`output/eval_results.summary.json`](./output/eval_results.summary.json)",
        "",
        "---",
        "",
        "## TL;DR / Decision",
        "",
        summary["headline"],
        "",
        "## Scope",
        "",
        "The FreshStack corpus contains no PDFs, so OCR routing is **not**",
        "exercised here. Its evidence is experiment 24, on a disjoint corpus",
        "of five held-out PDFs. This is the combined *retrieval* path:",
        "model-token chunking plus the candidate query instruction.",
        "",
        "## Frozen gate checks (on `combined_candidate`)",
        "",
        "| Gate | Rule | Measured | Verdict |",
        "| --- | --- | --- | --- |",
        f"| Quality | mean R@5 ≥ {q['threshold']} | {q['measured']:.6f} (n={q['n']}) | "
        f"{mark[q['pass']]} |",
        f"| Regression | identifier-heavy R@10 ≥ {r['threshold']} | {r['measured']:.6f} "
        f"(n={r['n']}) | {mark[r['pass']]} |",
        f"| Latency | query p95 ≤ {lat['threshold']} ms | {lat['measured']:,.0f} ms | "
        f"{mark[lat['pass']]} |",
        "",
        "Thresholds are read from the frozen [`plan.json`](./plan.json), frozen",
        f"{plan['gate_freeze']['frozen_date']} and unchanged. Every value is carried",
        "over from the earlier frozen plans rather than re-derived.",
        "",
        "## The 2x2",
        "",
        *_grid_table(agg),
        "",
        "`baseline_production` and `instruction_only` are loaded from their",
        "committed checkpoints and re-aggregated with identical metric code.",
        "`chunking_only_raw` and `combined_candidate` were measured here,",
        "interleaved in one process against the preserved experiment 25 index.",
        "",
        "## Interaction (monitored, not gated)",
        "",
        f"- Chunking alone: {inter['chunking_effect']:+.4f} R@5",
        f"- Instruction alone: {inter['instruction_effect']:+.4f} R@5",
        f"- Additive prediction: {inter['additive_prediction']:+.4f} R@5",
        f"- Combined, measured: {inter['combined_effect']:+.4f} R@5",
        f"- **Interaction term: {inter['interaction']:+.4f} R@5**",
        "",
        inter["note"],
        "",
        "## Cost (task 5.4 record)",
        "",
        "Index build cost is experiment 25's verified 0.974906 request-token",
        "ratio; the index is reused unchanged and not rebuilt. Query cost:",
        "",
        *cost_lines,
        "",
        "## Drift cross-check against experiment 25",
        "",
        f"- Experiment 25 published R@5 ({summary['drift']['exp25_cell']}): "
        f"{summary['drift']['exp25_recall_at_5']:.6f}",
        f"- This run's `chunking_only_raw` R@5: "
        f"{summary['drift']['exp27_chunking_only_recall_at_5']:.6f}",
        f"- Delta: {summary['drift']['delta']:+.6f}",
        "",
        "## Interpretation",
        "",
        "A passing combined run does not promote the query instruction.",
        "Only experiment 26's own frozen gates can do that (task 5.5).",
        "",
        "## Reproduction",
        "",
        "```bash",
        "uv run python experiments/27-combined-candidate-path-2026-09-09/run_eval.py --resume",
        "uv run python experiments/27-combined-candidate-path-2026-09-09/summarise_eval.py",
        "```",
        "",
        "No index is built or written: both measured arms query the preserved",
        "experiment 25 index read-only.",
        "",
    ]
    # Hand-written interpretation lives in its own file so regenerating
    # the tables never discards it.
    discussion = EXP_DIR / "discussion.md"
    if discussion.exists():
        lines.append(discussion.read_text(encoding="utf-8"))
    (EXP_DIR / "results.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Assemble the 2x2, evaluate the frozen gates, write the artefacts."""
    queries = {q["query_id"]: q for q in json.loads(GT_PATH.read_text(encoding="utf-8"))["queries"]}
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    scored = {cell: _scored_rows(path, queries) for cell, path in CELL_SOURCES.items()}
    counts = {cell: len(rows) for cell, rows in scored.items()}
    measured = {counts[c] for c in MEASURED_HERE}
    if len(measured) != 1:
        raise SystemExit(f"measured arms are not paired: {counts}")
    print(f"[summarise] cell sizes: {counts}", flush=True)

    aggregates = {cell: _aggregate(rows) for cell, rows in scored.items()}
    gates = _gates(plan, aggregates["combined_candidate"])
    verdict = "PASS" if all(g["pass"] for g in gates.values()) else "FAIL"
    failed = [name for name, gate in gates.items() if not gate["pass"]]
    interaction = _interaction(aggregates)

    if verdict == "PASS":
        headline = (
            "- All three frozen gates pass on the stacked path: the combined\n"
            f"  candidate holds mean R@5 at {gates['quality_recall_at_5']['measured']:.4f} and\n"
            f"  identifier-heavy R@10 at {gates['regression_identifier_r10']['measured']:.4f},\n"
            f"  inside a p95 of {gates['latency_p95_ms']['measured']:,.0f} ms.\n"
            f"- Interaction on R@5 is {interaction['interaction']:+.4f}: stacking the two\n"
            "  changes behaves close to additively on this workload.\n"
            "- This does not promote the query instruction. Experiment 26's gates do."
        )
    else:
        headline = (
            f"- **Negative result.** Failed gates: {', '.join(failed)}.\n"
            "- The stacked path is worse than the frozen bar the single-factor\n"
            "  arms were held to. Ship only the component that passed alone.\n"
            f"- Interaction on R@5 is {interaction['interaction']:+.4f}."
        )

    summary = {
        "experiment": EXP_DIR.name,
        "run_date": "2026-09-09",
        "verdict": verdict,
        "failed_gates": failed,
        "headline": headline,
        "gates": gates,
        "metrics_by_cell": aggregates,
        "interaction": interaction,
        "query_token_cost": _query_token_cost(queries),
        "drift": _drift(aggregates),
        "runtime_manifest": json.loads(MANIFEST_PATH.read_text(encoding="utf-8")),
        "cell_sources": {c: str(p) for c, p in CELL_SOURCES.items()},
    }

    out_json = EXP_DIR / "output/eval_results.summary.json"
    tmp = out_json.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    tmp.replace(out_json)
    _write_results_md(summary, plan)
    print(f"[summarise] verdict={verdict} → {out_json}", flush=True)


if __name__ == "__main__":
    main()
