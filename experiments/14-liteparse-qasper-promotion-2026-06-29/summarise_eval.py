"""Summarise Experiment 14: LiteParse promotion on Qasper.

Evaluates H1 (corpus validity), H2 (speed), H3 (reranker benefit),
and non-regression gates.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def _evaluate_gates(cells: list[dict[str, Any]], ingestion_times: dict[str, float]) -> dict[str, Any]:
    cell_map = {c["cell"]: c for c in cells}

    pypdf_off = cell_map.get("pypdf_off", {})
    pypdf_on = cell_map.get("pypdf_on", {})
    liteparse_off = cell_map.get("liteparse_off", {})
    liteparse_on = cell_map.get("liteparse_on", {})

    # H1: corpus validity — dense baseline < 100% Hit@5
    dense_hit5 = pypdf_off.get("metrics", {}).get("hit@5", 1.0)
    h1_pass = dense_hit5 < 1.0

    # H2: speed — LiteParse ingestion < pypdf ingestion
    pypdf_ingest = ingestion_times.get("pypdf", 0.0)
    liteparse_ingest = ingestion_times.get("liteparse", 0.0)
    h2_pass = liteparse_ingest < pypdf_ingest if pypdf_ingest > 0 and liteparse_ingest > 0 else False

    # H3: reranker lift — LiteParse > pypdf
    pypdf_rerank_lift = (
        pypdf_on.get("metrics", {}).get("coverage@20", 0.0)
        - pypdf_off.get("metrics", {}).get("coverage@20", 0.0)
    )
    liteparse_rerank_lift = (
        liteparse_on.get("metrics", {}).get("coverage@20", 0.0)
        - liteparse_off.get("metrics", {}).get("coverage@20", 0.0)
    )
    h3_pass = liteparse_rerank_lift > pypdf_rerank_lift

    # Non-regression: LiteParse Coverage@20 ≥ pypdf − 2pp
    liteparse_cov = liteparse_off.get("metrics", {}).get("coverage@20", 0.0)
    pypdf_cov = pypdf_off.get("metrics", {}).get("coverage@20", 0.0)
    non_regression_pass = liteparse_cov >= pypdf_cov - 0.02

    # Recommendation
    if not h1_pass:
        recommendation = (
            "H1 FAILED: Dense baseline achieves 100% Hit@5. "
            "Corpus is still too easy — need an even harder corpus."
        )
    elif not non_regression_pass:
        recommendation = (
            "NON-REGRESSION FAILED: LiteParse Coverage@20 regresses > 2pp vs pypdf. "
            "Do NOT promote LiteParse default."
        )
    elif h3_pass and h2_pass:
        recommendation = (
            "ALL GATES PASSED. LiteParse benefits more from reranking and is faster. "
            "Promote PDF_READER=auto (LiteParse default). Draft ADR-020 amendment."
        )
    elif h2_pass and non_regression_pass:
        recommendation = (
            "H2 + non-regression pass, but H3 inconclusive. "
            "LiteParse promotion justified on speed grounds. "
            "Reranker benefit is reader-independent."
        )
    else:
        recommendation = (
            "Mixed results. Review per-cell metrics before deciding."
        )

    return {
        "h1_corpus_validity": {"pass": h1_pass, "dense_hit5": round(dense_hit5, 6)},
        "h2_speed": {
            "pass": h2_pass,
            "pypdf_ingestion_s": pypdf_ingest,
            "liteparse_ingestion_s": liteparse_ingest,
        },
        "h3_reranker_benefit": {
            "pass": h3_pass,
            "pypdf_rerank_lift": round(pypdf_rerank_lift, 6),
            "liteparse_rerank_lift": round(liteparse_rerank_lift, 6),
        },
        "non_regression": {
            "pass": non_regression_pass,
            "pypdf_cov20": round(pypdf_cov, 6),
            "liteparse_cov20": round(liteparse_cov, 6),
        },
        "recommendation": recommendation,
    }


def _write_results_md(
    data: dict[str, Any],
    summary: dict[str, Any],
    path: Path,
) -> None:
    cells = {c["cell"]: c for c in data.get("cells", [])}

    lines = [
        "# Experiment 14 Results: LiteParse Promotion on Qasper",
        "",
        f"**Recommendation:** {summary['recommendation']}",
        "",
        "## Gate summary",
        "",
        f"| Gate | Result | Detail |",
        f"| --- | :--: | --- |",
        f"| H1: Corpus validity | {'✅' if summary['h1_corpus_validity']['pass'] else '❌'} | "
        f"Dense Hit@5={summary['h1_corpus_validity']['dense_hit5']:.4f} |",
        f"| H2: Speed | {'✅' if summary['h2_speed']['pass'] else '❌'} | "
        f"pypdf={summary['h2_speed']['pypdf_ingestion_s']:.1f}s, "
        f"liteparse={summary['h2_speed']['liteparse_ingestion_s']:.1f}s |",
        f"| H3: Reranker benefit | {'✅' if summary['h3_reranker_benefit']['pass'] else '❌'} | "
        f"pypdf lift={summary['h3_reranker_benefit']['pypdf_rerank_lift']:+.4f}, "
        f"liteparse lift={summary['h3_reranker_benefit']['liteparse_rerank_lift']:+.4f} |",
        f"| Non-regression | {'✅' if summary['non_regression']['pass'] else '❌'} | "
        f"pypdf Cov@20={summary['non_regression']['pypdf_cov20']:.4f}, "
        f"liteparse Cov@20={summary['non_regression']['liteparse_cov20']:.4f} |",
        "",
        "## Cell metrics",
        "",
        "| Cell | Coverage@20 | Hit@5 | Hit@10 | MRR@10 | P95 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    for cell_name in ["pypdf_off", "pypdf_on", "liteparse_off", "liteparse_on"]:
        cell = cells.get(cell_name, {})
        m = cell.get("metrics", {})
        lines.append(
            f"| {cell_name} | {m.get('coverage@20', 0):.4f} | {m.get('hit@5', 0):.4f} | "
            f"{m.get('hit@10', 0):.4f} | {m.get('mrr@10', 0):.4f} | "
            f"{m.get('p95_ms', 0):.0f} |"
        )

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=SCRIPT_DIR / "output" / "eval_results.json")
    parser.add_argument("--output", type=Path, default=SCRIPT_DIR / "output" / "eval_results.summary.json")
    parser.add_argument("--results-md", type=Path, default=SCRIPT_DIR / "output" / "results.md")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    ingestion_times = data.get("settings", {}).get("ingestion_times", {})
    summary = _evaluate_gates(data.get("cells", []), ingestion_times)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_results_md(data, summary, args.results_md)
    print(f"Summary written to {args.output}")
    print(f"Results report written to {args.results_md}")
    print(summary["recommendation"])


if __name__ == "__main__":
    main()
