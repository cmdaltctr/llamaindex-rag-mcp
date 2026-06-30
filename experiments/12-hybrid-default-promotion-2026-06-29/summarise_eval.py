"""Summarise Experiment 12: Hybrid Default Promotion Test.

Computes bootstrap 95% confidence intervals on the Coverage@20 lift
(hybrid_off vs dense_off), evaluates pass gates, and writes results.md.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def _bootstrap_ci(
    values: list[float],
    n_bootstrap: int = 10000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """Compute bootstrap confidence interval for the mean."""
    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_bootstrap):
        sample = [rng.choice(values) for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    alpha = (1 - confidence) / 2
    lo_idx = int(n_bootstrap * alpha)
    hi_idx = int(n_bootstrap * (1 - alpha))
    return means[lo_idx], means[hi_idx]


def _per_query_coverage(
    cell: dict[str, Any],
    qrels: dict[str, dict[str, int]],
    k: int,
) -> list[float]:
    """Get per-query coverage@k (1.0 if any hit, 0.0 otherwise)."""
    values = []
    for result in cell.get("per_query", []):
        query_id = result["query_id"]
        retrieved_ids = [r["id"] for r in result["retrieved"][:k]]
        relevant = qrels.get(query_id, {})
        relevant_set = {doc_id for doc_id, rel in relevant.items() if rel > 0}
        if relevant_set:
            hit = any(doc_id in relevant_set for doc_id in retrieved_ids)
            values.append(1.0 if hit else 0.0)
    return values


def _pass_criteria(
    cells: dict[str, dict[str, Any]],
    qrels: dict[str, dict[str, int]],
    semantic_query_ids: set[str],
) -> dict[str, Any]:
    """Evaluate pass gates."""
    dense_off = cells.get("dense-only__rerank_off", {})
    hybrid_off = cells.get("hybrid_bm25__rerank_off", {})

    dense_cov20 = dense_off.get("metrics", {}).get("coverage@20", 0.0)
    hybrid_cov20 = hybrid_off.get("metrics", {}).get("coverage@20", 0.0)
    lift = hybrid_cov20 - dense_cov20

    # Bootstrap CI on lift
    dense_per_query = _per_query_coverage(dense_off, qrels, 20)
    hybrid_per_query = _per_query_coverage(hybrid_off, qrels, 20)
    if len(dense_per_query) == len(hybrid_per_query):
        diffs = [h - d for h, d in zip(hybrid_per_query, dense_per_query)]
    else:
        diffs = []
    ci_lo, ci_hi = _bootstrap_ci(diffs) if diffs else (0.0, 0.0)

    # Semantic guardrail
    dense_sem_cov20 = dense_off.get("metrics_semantic", {}).get("coverage@20", 0.0)
    hybrid_sem_cov20 = hybrid_off.get("metrics_semantic", {}).get("coverage@20", 0.0)
    sem_regression = dense_sem_cov20 - hybrid_sem_cov20

    # Pass gates
    lift_pass = lift >= 0.03
    ci_pass = ci_lo > 0
    sem_pass = sem_regression <= 0.02

    # Non-regression check
    non_regression_pass = True
    for metric in ["recall@50", "ndcg@10", "hit@10", "mrr@10"]:
        dense_val = dense_off.get("metrics", {}).get(metric, 0.0)
        hybrid_val = hybrid_off.get("metrics", {}).get(metric, 0.0)
        if dense_val - hybrid_val > 0.05:
            non_regression_pass = False
            break

    all_pass = lift_pass and ci_pass and sem_pass and non_regression_pass

    if all_pass:
        recommendation = (
            f"RECOMMEND promoting HYBRID_ENABLED=true. "
            f"Coverage@20 lift={lift:.1%} (≥3pp), 95% CI=[{ci_lo:.1%}, {ci_hi:.1%}] "
            f"(excludes zero), semantic regression={sem_regression:.1%} (≤2pp). "
            f"Draft ADR-016 amendment (separate change)."
        )
    elif not lift_pass:
        recommendation = (
            f"Do NOT promote hybrid. Coverage@20 lift={lift:.1%} < 3pp. "
            f"Keep dense-only default."
        )
    elif not ci_pass:
        recommendation = (
            f"Do NOT promote hybrid. Coverage@20 lift={lift:.1%} but 95% CI "
            f"[{ci_lo:.1%}, {ci_hi:.1%}] includes zero. Not statistically significant."
        )
    elif not sem_pass:
        recommendation = (
            f"Do NOT promote hybrid. Semantic regression={sem_regression:.1%} > 2pp. "
            f"Hybrid helps technical but hurts semantic queries."
        )
    else:
        recommendation = (
            f"Do NOT promote hybrid. Non-regression check failed. "
            f"Some metrics regressed by more than 5pp."
        )

    return {
        "coverage_lift": round(lift, 6),
        "ci_95": [round(ci_lo, 6), round(ci_hi, 6)],
        "ci_excludes_zero": ci_pass,
        "semantic_regression": round(sem_regression, 6),
        "lift_pass": lift_pass,
        "ci_pass": ci_pass,
        "sem_pass": sem_pass,
        "non_regression_pass": non_regression_pass,
        "all_gates_pass": all_pass,
        "recommendation": recommendation,
    }


def _write_results_md(
    data: dict[str, Any],
    pass_criteria: dict[str, Any],
    path: Path,
) -> None:
    cells = {c["cell"]: c for c in data.get("cells", [])}

    lines = [
        "# Experiment 12 Results: Hybrid Default Promotion Test",
        "",
        f"**Recommendation:** {pass_criteria['recommendation']}",
        "",
        "## Corpus and setup",
        "",
        f"- Total queries: {data.get('settings', {}).get('total_queries')}",
        f"- Semantic queries: {data.get('settings', {}).get('semantic_queries')}",
        f"- Embedding model: {data.get('settings', {}).get('embed_model')}",
        f"- RRF k: {data.get('settings', {}).get('hybrid_rrf_k')}",
        f"- Post-ADR-021 config: MULTIPLIER={data.get('settings', {}).get('rerank_fetch_multiplier')}, "
        f"MAX_FETCH={data.get('settings', {}).get('rerank_max_fetch')}",
        "",
        "## Pass gates",
        "",
        f"| Gate | Criterion | Result | Pass? |",
        f"| --- | --- | ---: | :--: |",
        f"| Coverage@20 lift | ≥ 3pp | {pass_criteria['coverage_lift']:.1%} | {'✅' if pass_criteria['lift_pass'] else '❌'} |",
        f"| 95% CI excludes zero | CI lo > 0 | [{pass_criteria['ci_95'][0]:.1%}, {pass_criteria['ci_95'][1]:.1%}] | {'✅' if pass_criteria['ci_pass'] else '❌'} |",
        f"| Semantic guardrail | ≤ 2pp regression | {pass_criteria['semantic_regression']:.1%} | {'✅' if pass_criteria['sem_pass'] else '❌'} |",
        f"| Non-regression | No metric > 5pp regression | — | {'✅' if pass_criteria['non_regression_pass'] else '❌'} |",
        "",
        "## Cell metrics (all queries)",
        "",
        "| Cell | Coverage@20 | Recall@50 | α-nDCG@10 | Hit@10 | MRR@10 | P95 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for cell_name in ["dense-only__rerank_off", "hybrid_bm25__rerank_off", "dense-only__rerank_on", "hybrid_bm25__rerank_on"]:
        cell = cells.get(cell_name, {})
        m = cell.get("metrics", {})
        lines.append(
            f"| {cell_name} | {m.get('coverage@20', 0):.4f} | {m.get('recall@50', 0):.4f} | "
            f"{m.get('ndcg@10', 0):.4f} | {m.get('hit@10', 0):.4f} | "
            f"{m.get('mrr@10', 0):.4f} | {m.get('p95_ms', 0):.0f} |"
        )

    lines.extend([
        "",
        "## Semantic query metrics",
        "",
        "| Cell | Coverage@20 | Recall@50 | α-nDCG@10 |",
        "| --- | ---: | ---: | ---: |",
    ])

    for cell_name in ["dense-only__rerank_off", "hybrid_bm25__rerank_off"]:
        cell = cells.get(cell_name, {})
        m = cell.get("metrics_semantic", {})
        lines.append(
            f"| {cell_name} | {m.get('coverage@20', 0):.4f} | {m.get('recall@50', 0):.4f} | "
            f"{m.get('ndcg@10', 0):.4f} |"
        )

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=SCRIPT_DIR / "output" / "eval_results.json")
    parser.add_argument("--output", type=Path, default=SCRIPT_DIR / "output" / "eval_results.summary.json")
    parser.add_argument("--results-md", type=Path, default=SCRIPT_DIR / "output" / "results.md")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))

    # Load qrels for bootstrap CI
    gt_path = SCRIPT_DIR / "ground-truth.json"
    if not gt_path.exists():
        gt_path = SCRIPT_DIR / "freshstack-qrels.json"
    qrels: dict[str, dict[str, int]] = {}
    gt: dict[str, Any] = {}
    if gt_path.exists():
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        qrels = gt.get("qrels", {})

    # Identify semantic queries
    semantic_query_ids: set[str] = set()
    for q in gt.get("queries", []):
        if not q.get("is_identifier_heavy", False):
            semantic_query_ids.add(q["id"])

    cells = {c["cell"]: c for c in data.get("cells", [])}
    pass_criteria = _pass_criteria(cells, qrels, semantic_query_ids)

    summary = {
        "experiment": data.get("experiment"),
        "pass_criteria": pass_criteria,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_results_md(data, pass_criteria, args.results_md)
    print(f"Summary written to {args.output}")
    print(f"Results report written to {args.results_md}")
    print(pass_criteria["recommendation"])


if __name__ == "__main__":
    main()
