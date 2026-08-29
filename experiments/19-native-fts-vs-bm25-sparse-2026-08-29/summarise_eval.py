"""Experiment 19 summariser: aggregate cells, evaluate gates, write results.md.

Reads ``output/cells/{bm25,native}.json`` (written by ``run_eval.py``),
computes quality/latency/determinism/memory comparisons, evaluates the
pre-registered pass gates from protocol.md, and writes
``output/eval_results.summary.json`` plus ``results.md``.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
GT_PATH = EXP_DIR.parent / "9-hybrid-retrieval-2026-05-27/ground-truth.json"
CELLS_DIR = EXP_DIR / "output/cells"
SUMMARY_JSON = EXP_DIR / "output/eval_results.summary.json"
RESULTS_MD = EXP_DIR / "results.md"


def _recall_mrr(rows: list[dict], k: int) -> tuple[float, float]:
    """Recall@k and MRR@k against ``expected_source``."""
    hits = 0
    reciprocal = 0.0
    for row in rows:
        top_sources = row["sources"][:k]
        if any(_src_match(s, row["expected_source"]) for s in top_sources):
            hits += 1
            first = next(
                i + 1 for i, s in enumerate(top_sources) if _src_match(s, row["expected_source"])
            )
            reciprocal += 1.0 / first
    n = len(rows)
    return (hits / n if n else 0.0), (reciprocal / n if n else 0.0)


def _src_match(source: str, expected: str) -> bool:
    name = Path(source or "").name
    return name == expected or expected in name


def _by_category(rows: list[dict], k: int) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    categories = sorted({row["category"] for row in rows})
    for category in categories:
        subset = [row for row in rows if row["category"] == category]
        recall, mrr = _recall_mrr(subset, k)
        out[category] = {"recall": round(recall, 4), "mrr": round(mrr, 4)}
    return out


def _pctl(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(int(q * len(ordered)), len(ordered) - 1)
    return ordered[idx]


def summarise_cell(cell: dict) -> dict:
    """Compute per-cell metrics from a cell payload."""
    warm_rows = cell["sparse"]["warm"]["rows"]
    sparse_recall5, _ = _recall_mrr(warm_rows, 5)
    sparse_recall10, sparse_mrr10 = _recall_mrr(warm_rows, 10)
    hybrid_recall5, _ = _recall_mrr(cell["hybrid"]["rows"], 5)
    hybrid_recall10, hybrid_mrr10 = _recall_mrr(cell["hybrid"]["rows"], 10)
    warm_t = cell["sparse"]["warm"]["timings_s"]
    cold_t = cell["sparse"]["cold"]["timings_s"]
    return {
        "cell": cell["cell"],
        "sparse_only": {
            "recall@5": round(sparse_recall5, 4),
            "recall@10": round(sparse_recall10, 4),
            "mrr@10": round(sparse_mrr10, 4),
            "by_category@10": _by_category(warm_rows, 10),
            "cold_first_query_ms": round(cold_t[0] * 1000, 3) if cold_t else None,
        },
        "hybrid": {
            "recall@5": round(hybrid_recall5, 4),
            "recall@10": round(hybrid_recall10, 4),
            "mrr@10": round(hybrid_mrr10, 4),
            "by_category@10": _by_category(cell["hybrid"]["rows"], 10),
        },
        "latency": {
            "warm_p50_ms": round(statistics.median(warm_t) * 1000, 3) if warm_t else None,
            "warm_p95_ms": round(_pctl(warm_t, 0.95) * 1000, 3),
            "cold_first_query_ms": round(cold_t[0] * 1000, 3) if cold_t else None,
            "cold_total_s": round(sum(cold_t), 3),
        },
        "determinism_mismatches": cell["sparse"]["determinism_mismatches"],
        "memory": cell["memory"],
    }


def main() -> None:
    """Aggregate cells, evaluate gates, write summary + results.md."""
    bm25 = json.loads((CELLS_DIR / "bm25.json").read_text())
    native = json.loads((CELLS_DIR / "native.json").read_text())
    m = summarise_cell(bm25)
    n = summarise_cell(native)

    native_delta_pp = round(
        (n["sparse_only"]["recall@10"] - m["sparse_only"]["recall@10"]) * 100, 2
    )
    # Compute from raw timings: the 4-dp metric rounding zeroes BM25's
    # sub-millisecond warm p50 on this corpus scale.
    bm25_warm_p50 = statistics.median(bm25["sparse"]["warm"]["timings_s"])
    native_warm_p50 = statistics.median(native["sparse"]["warm"]["timings_s"])
    latency_ratio = round(native_warm_p50 / bm25_warm_p50, 1) if bm25_warm_p50 > 0 else None
    rss_delta_pct = round(
        (n["memory"]["peak_rss_mb"] - m["memory"]["peak_rss_mb"])
        / max(m["memory"]["peak_rss_mb"], 1)
        * 100,
        1,
    )

    gates = {
        "G1_quality_floor_-2pp": native_delta_pp >= -2.0,
        "G2_determinism_zero_mismatches": (
            n["determinism_mismatches"] == 0 and m["determinism_mismatches"] == 0
        ),
        "G3_latency_within_10x": latency_ratio is not None and latency_ratio <= 10.0,
        "G4_memory_within_10pct": rss_delta_pct <= 10.0,
    }
    promotion_quality_win = native_delta_pp >= 2.0

    summary = {
        "bm25": m,
        "native": n,
        "comparison": {
            "sparse_recall@10_delta_pp": native_delta_pp,
            "warm_p50_ms": {
                "bm25": m["latency"]["warm_p50_ms"],
                "native": n["latency"]["warm_p50_ms"],
            },
            "warm_p50_latency_ratio_native_over_bm25": latency_ratio,
            "peak_rss_delta_pct": rss_delta_pct,
        },
        "gates": gates,
        "promotion": {
            "quality_win_ge_2pp": promotion_quality_win,
            "all_gates_pass": all(gates.values()),
            "decision": "KEEP bm25 DEFAULT"
            if not (promotion_quality_win and all(gates.values()))
            else "CANDIDATE FOR PROMOTION (requires user sign-off)",
        },
    }
    tmp = SUMMARY_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(summary, indent=2))
    tmp.replace(SUMMARY_JSON)

    lines = [
        "# Experiment 19 results: native FTS vs BM25 sparse backend",
        "",
        f"**Status:** {'PASS' if all(gates.values()) else 'FAIL'} "
        f"(gates) — decision: {summary['promotion']['decision']}",
        f"**Ran:** 2026-08-29 · corpus: Exp 9 packs · store chunks: {bm25['chunk_count']}",
        "",
        "## Quality (sparse-only, warm)",
        "",
        "| Metric | BM25 | Native |",
        "| --- | --- | --- |",
        f"| Recall@5 | {m['sparse_only']['recall@5']:.3f} | {n['sparse_only']['recall@5']:.3f} |",
        f"| Recall@10 | {m['sparse_only']['recall@10']:.3f} | {n['sparse_only']['recall@10']:.3f} |",
        f"| MRR@10 | {m['sparse_only']['mrr@10']:.3f} | {n['sparse_only']['mrr@10']:.3f} |",
        "",
        "Per category (sparse-only Recall@10):",
        "",
        "| Category | BM25 | Native |",
        "| --- | --- | --- |",
    ]
    for category in sorted(m["sparse_only"]["by_category@10"]):
        lines.append(
            f"| {category} | {m['sparse_only']['by_category@10'][category]['recall']:.3f} "
            f"| {n['sparse_only']['by_category@10'].get(category, {}).get('recall', float('nan')):.3f} |"
        )
    lines += [
        "",
        "## Quality (hybrid fused, warm)",
        "",
        "| Metric | BM25 | Native |",
        "| --- | --- | --- |",
        f"| Recall@10 | {m['hybrid']['recall@10']:.3f} | {n['hybrid']['recall@10']:.3f} |",
        f"| MRR@10 | {m['hybrid']['mrr@10']:.3f} | {n['hybrid']['mrr@10']:.3f} |",
        "",
        "## Latency (sparse query, milliseconds)",
        "",
        "| Phase | BM25 | Native |",
        "| --- | --- | --- |",
        f"| Cold first query | {m['latency']['cold_first_query_ms']} ms | {n['latency']['cold_first_query_ms']} ms |",
        f"| Warm p50 | {m['latency']['warm_p50_ms']} ms | {n['latency']['warm_p50_ms']} ms |",
        f"| Warm p95 | {m['latency']['warm_p95_ms']} ms | {n['latency']['warm_p95_ms']} ms |",
        "",
        f"Native/BM25 warm p50 ratio: **{latency_ratio}×**",
        "",
        "## Determinism and memory",
        "",
        "| Metric | BM25 | Native |",
        "| --- | --- | --- |",
        f"| Ordering mismatches (warm 2 vs 3) | {m['determinism_mismatches']} | {n['determinism_mismatches']} |",
        f"| tracemalloc cold peak (MB) | {m['memory']['tracemalloc_cold_peak_mb']} | {n['memory']['tracemalloc_cold_peak_mb']} |",
        f"| Peak RSS (MB) | {m['memory']['peak_rss_mb']} | {n['memory']['peak_rss_mb']} |",
        "",
        f"Peak RSS delta (native vs bm25): **{rss_delta_pct}%**",
        "",
        "## Gates",
        "",
    ]
    for gate, passed in gates.items():
        lines.append(f"- {'✅' if passed else '❌'} {gate}")
    lines += [
        "",
        f"Quality delta (native − bm25, sparse Recall@10): **{native_delta_pp:+.2f} pp**",
        "",
        "## Recommendation",
        "",
    ]
    if summary["promotion"]["decision"] == "KEEP bm25 DEFAULT":
        lines += [
            "The default stays `bm25`. Native FTS is a registered,",
            "capability-resolved alternative with lifecycle and fallback",
            "guarantees; these results are the standing evidence for the",
            "default decision. Revisit only with a larger, more",
            "representative corpus or changed pass gates (protocol",
            "pre-registration).",
        ]
    else:
        lines += [
            "Native meets the pre-registered promotion criteria. Default",
            "promotion STILL requires explicit user sign-off per the",
            "protocol's promotion rule.",
        ]
    RESULTS_MD.write_text("\n".join(lines) + "\n")
    print(json.dumps(summary["comparison"], indent=2))
    print(json.dumps(gates, indent=2))
    print(f"[summarise] wrote {SUMMARY_JSON} and {RESULTS_MD}")


if __name__ == "__main__":
    main()
