"""Experiment 27 assembly diagnostics: gates, interaction, cost, drift, grid.

Split out of ``summarise_eval.py`` (repair change, 2026-09-10) to keep
each file under the 500-line budget, following the multi-module layout
experiment 25 already uses. Pure functions except the two offline file
readers (manifest, experiment 25 summary); no network access.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
EXP25_DIR = EXP_DIR.parent / "25-token-chunking-ablation-2026-09-08"
MANIFEST_PATH = EXP_DIR / "output/runtime_manifest.json"


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


def _query_token_cost(queries: dict, *, runtime_manifest: dict | None = None) -> dict:
    """Mean request tokens per query, raw vs instructed (offline).

    Counted with the pinned tokenizer from the local cache — no API call
    and no spend. Degrades to ``available: False`` when the tokenizer is
    not cached.
    """
    manifest = (
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if runtime_manifest is None
        else runtime_manifest
    )
    instruction = manifest["embedding"]["candidate_instruction"]
    try:
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
    key = "model_token_markdown"
    if key not in cells:
        return {
            "available": False,
            "reason": "experiment 25 summary lacks the model_token_markdown cell; "
            "no arbitrary cell is substituted for the comparison",
        }
    prior = cells[key]["all"]["recall_at_5"]
    local = aggregates["chunking_only_raw"]["all"]["recall_at_5"]
    return {
        "available": True,
        "exp25_cell": key,
        "exp25_recall_at_5": prior,
        "exp27_chunking_only_recall_at_5": local,
        "delta": round(local - prior, 6),
        "note": "same index and queries on different dates; a non-zero delta "
        "is consistent with provider-side or pipeline variance between runs "
        "and does not by itself identify a cause",
    }


def _grid_table(aggregates: dict, *, historical: bool = True) -> list[str]:
    """The 2x2 rendered as a table, with each cell's measurement date."""
    labels = {
        "baseline_production": ("legacy chars", "raw", "2026-09-07 (exp 22)"),
        "instruction_only": ("legacy chars", "instructed", "2026-09-09 (exp 26)"),
        "chunking_only_raw": ("model tokens", "raw", "2026-09-09 (here)"),
        "combined_candidate": ("model tokens", "instructed", "2026-09-09 (here)"),
    }
    lines = [
        "| Cell | Chunking | Query | Measured | R@1 | R@3 | R@5 | R@10 | MRR@10 | P95 |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for cell, (chunk, query, date) in labels.items():
        if not historical and cell in {"chunking_only_raw", "combined_candidate"}:
            date = "see recorded session"
        row = aggregates[cell]["all"]
        lines.append(
            f"| {cell} | {chunk} | {query} | {date} | "
            + " | ".join(
                f"{row[k] * 100:.1f}%"
                for k in ("recall_at_1", "recall_at_3", "recall_at_5", "recall_at_10", "mrr_at_10")
            )
            + f" | {row['p95_latency_ms']:,.0f} ms |"
        )
    return lines
