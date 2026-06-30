"""Summarise Experiment 9a-rerun: Post-ADR-021 Reranker Validation.

Compares results to original Exp 9a (fetch_k=500 vs fetch_k=150) and
determines whether ADR-019 is validated, uncertain, or invalidated.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
EXP9A_DIR = SCRIPT_DIR.parent / "9a-hybrid-retrieval-freshstack-langchain-2026-05-30"


def _pass_criteria(cells: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Evaluate pass gates."""
    dense_off = cells.get("dense-only__rerank_off", {})
    dense_on = cells.get("dense-only__rerank_on", {})
    hybrid_off = cells.get("hybrid_bm25__rerank_off", {})
    hybrid_on = cells.get("hybrid_bm25__rerank_on", {})

    dense_off_cov = dense_off.get("metrics", {}).get("coverage@20", 0.0)
    dense_on_cov = dense_on.get("metrics", {}).get("coverage@20", 0.0)
    hybrid_off_cov = hybrid_off.get("metrics", {}).get("coverage@20", 0.0)
    hybrid_on_cov = hybrid_on.get("metrics", {}).get("coverage@20", 0.0)

    dense_degradation = dense_off_cov - dense_on_cov
    hybrid_degradation = hybrid_off_cov - hybrid_on_cov

    reranker_degrades = dense_degradation > 0 and hybrid_degradation > 0
    within_1pp = abs(dense_degradation) <= 0.01 and abs(hybrid_degradation) <= 0.01

    if reranker_degrades:
        conclusion = "VALIDATED"
        recommendation = (
            f"ADR-019 VALIDATED. Reranker still degrades Coverage@20 at fetch_k=150: "
            f"dense degradation={dense_degradation:.1%}, hybrid degradation={hybrid_degradation:.1%}. "
            f"Reranker should remain disabled by default."
        )
    elif within_1pp:
        conclusion = "UNCERTAIN"
        recommendation = (
            f"ADR-019 UNCERTAIN. Reranker impact is within ±1pp at fetch_k=150: "
            f"dense delta={dense_degradation:.1%}, hybrid delta={hybrid_degradation:.1%}. "
            f"Recommend Exp 10b for deeper pool-size investigation."
        )
    else:
        conclusion = "INVALIDATED"
        recommendation = (
            f"ADR-019 may need amendment. Reranker improves Coverage@20 at fetch_k=150: "
            f"dense delta={dense_degradation:.1%}, hybrid delta={hybrid_degradation:.1%}. "
            f"The reduced pool size may fix the reranker. Draft ADR-019 amendment (separate change)."
        )

    # Latency comparison
    dense_on_p95 = dense_on.get("metrics", {}).get("p95_ms", 0.0)
    hybrid_on_p95 = hybrid_on.get("metrics", {}).get("p95_ms", 0.0)

    return {
        "conclusion": conclusion,
        "dense_degradation": round(dense_degradation, 6),
        "hybrid_degradation": round(hybrid_degradation, 6),
        "reranker_degrades": reranker_degrades,
        "within_1pp": within_1pp,
        "dense_on_p95_ms": dense_on_p95,
        "hybrid_on_p95_ms": hybrid_on_p95,
        "recommendation": recommendation,
    }


def _load_exp9a_results() -> dict[str, Any] | None:
    """Load original Exp 9a results for comparison."""
    exp9a_results = EXP9A_DIR / "output" / "eval_results.json"
    if exp9a_results.exists():
        return json.loads(exp9a_results.read_text(encoding="utf-8"))
    exp9a_results = EXP9A_DIR / "eval_results.json"
    if exp9a_results.exists():
        return json.loads(exp9a_results.read_text(encoding="utf-8"))
    return None


def _write_results_md(
    data: dict[str, Any],
    pass_criteria: dict[str, Any],
    exp9a: dict[str, Any] | None,
    path: Path,
) -> None:
    cells = {c["cell"]: c for c in data.get("cells", [])}

    lines = [
        "# Experiment 9a-rerun Results: Post-ADR-021 Reranker Validation",
        "",
        f"**Recommendation:** {pass_criteria['recommendation']}",
        "",
        "## Setup",
        "",
        f"- Effective fetch_k: {data.get('settings', {}).get('effective_fetch_k')}",
        f"- Config: MULTIPLIER={data.get('settings', {}).get('rerank_fetch_multiplier')}, "
        f"MAX_FETCH={data.get('settings', {}).get('rerank_max_fetch')}",
        f"- Queries: {data.get('settings', {}).get('total_queries')} "
        f"(technical: {data.get('settings', {}).get('technical_queries')}, "
        f"semantic: {data.get('settings', {}).get('semantic_queries')})",
        "",
        "## Cell metrics (all queries)",
        "",
        "| Cell | Coverage@20 | Recall@50 | α-nDCG@10 | Hit@10 | MRR@10 | P95 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for cell_name in ["dense-only__rerank_off", "dense-only__rerank_on", "hybrid_bm25__rerank_off", "hybrid_bm25__rerank_on"]:
        cell = cells.get(cell_name, {})
        m = cell.get("metrics", {})
        lines.append(
            f"| {cell_name} | {m.get('coverage@20', 0):.4f} | {m.get('recall@50', 0):.4f} | "
            f"{m.get('ndcg@10', 0):.4f} | {m.get('hit@10', 0):.4f} | "
            f"{m.get('mrr@10', 0):.4f} | {m.get('p95_ms', 0):.0f} |"
        )

    lines.extend([
        "",
        "## Pass gates",
        "",
        f"- **Reranker degradation (dense)**: {pass_criteria['dense_degradation']:.1%}",
        f"- **Reranker degradation (hybrid)**: {pass_criteria['hybrid_degradation']:.1%}",
        f"- **Conclusion**: {pass_criteria['conclusion']}",
        "",
    ])

    if exp9a:
        exp9a_cells = {c["cell"]: c for c in exp9a.get("cells", [])}
        lines.extend([
            "## Comparison to original Exp 9a (fetch_k=500)",
            "",
            "| Cell | 9a Coverage@20 | 9a-rerun Coverage@20 | Delta |",
            "| --- | ---: | ---: | ---: |",
        ])
        for cell_name in ["dense-only__rerank_off", "dense-only__rerank_on", "hybrid_bm25__rerank_off", "hybrid_bm25__rerank_on"]:
            orig = exp9a_cells.get(cell_name, {}).get("metrics", {}).get("coverage@20", 0.0)
            rerun = cells.get(cell_name, {}).get("metrics", {}).get("coverage@20", 0.0)
            delta = rerun - orig
            lines.append(f"| {cell_name} | {orig:.4f} | {rerun:.4f} | {delta:+.4f} |")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=SCRIPT_DIR / "output" / "eval_results.json")
    parser.add_argument("--output", type=Path, default=SCRIPT_DIR / "output" / "eval_results.summary.json")
    parser.add_argument("--results-md", type=Path, default=SCRIPT_DIR / "output" / "results.md")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    cells = {c["cell"]: c for c in data.get("cells", [])}
    pass_criteria = _pass_criteria(cells)
    exp9a = _load_exp9a_results()

    summary = {
        "experiment": data.get("experiment"),
        "pass_criteria": pass_criteria,
        "exp9a_comparison_loaded": exp9a is not None,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_results_md(data, pass_criteria, exp9a, args.results_md)
    print(f"Summary written to {args.output}")
    print(f"Results report written to {args.results_md}")
    print(pass_criteria["recommendation"])


if __name__ == "__main__":
    main()
