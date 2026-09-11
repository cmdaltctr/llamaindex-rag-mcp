"""Experiment 25 summariser: aggregate cells, evaluate frozen gates, write results.md.

Metric definitions are ported verbatim from Experiment 22's summariser
(``_rank_map``, ``_alpha_ndcg``, ``_metrics_for_query``, ``_aggregate``),
itself ported from 9a — so candidate numbers stay comparable with the
baseline. The baseline arm is loaded from Experiment 22's
``hybrid__raw`` checkpoint (not re-executed) and re-aggregated with the
same code; a cross-check against Experiment 22's published summary
aborts the run if the port drifts.

Gate thresholds are read from the frozen ``plan.json`` (never edited
after results exist). Comparisons use unrounded values; display
rounding happens only in formatting (``report.py``).

Writes:
- output/eval_results.summary.json  (aggregates, gates, runtime manifest)
- results.md                        (rendered by ``report.py``)
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from pathlib import Path

from report import write_results_md

EXP_DIR = Path(__file__).resolve().parent
EXP22_DIR = EXP_DIR.parent / "22-raw-query-qwen4b-baseline-2026-09-07"
GT_PATH = EXP22_DIR / "output/ground-truth.json"
QRELS_PATH = EXP22_DIR / "output/freshstack-qrels.json"
BASELINE_CKPT = EXP22_DIR / "output/cells/hybrid__raw.json"
BASELINE_SUMMARY = EXP22_DIR / "output/eval_results.summary.json"
CANDIDATE_CKPT = EXP_DIR / "output/cells/model_token_markdown.json"
PLAN_PATH = EXP_DIR / "plan.json"
BUILD_DONE = EXP_DIR / "output/build_done.json"
VERIFY_BASELINE = EXP_DIR / "output/verify_accounting_baseline.json"
VERIFY_CANDIDATE = EXP_DIR / "output/verify_accounting_candidate.json"

K_VALUES = (1, 3, 5, 10, 20, 50)


# ---------------------------------------------------------------------
# Metric functions — verbatim port from Experiment 22's summariser.
# Do not modify: comparability with the baseline depends on identity.
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
# Gate evaluation (unrounded comparisons against frozen thresholds)
# ---------------------------------------------------------------------
def _unrounded(rows: list[dict], key: str, category: str | None = None) -> float:
    """Unrounded mean of a per-query metric, optionally within one category."""
    selected = rows if category is None else [r for r in rows if r["category"] == category]
    return statistics.fmean(r["metrics"][key] for r in selected)


def _unrounded_p95_ms(rows: list[dict]) -> float:
    """Unrounded p95 latency in milliseconds (same order statistic as _aggregate)."""
    latencies = sorted(r["latency_s"] * 1000 for r in rows)
    return latencies[max(0, math.ceil(0.95 * len(latencies)) - 1)]


def _evaluate_gates(plan: dict, cand_rows: list[dict]) -> tuple[dict, bool]:
    """Compare unrounded candidate values against the frozen plan thresholds."""
    spec = {g["kind"]: g for g in plan["validity_gates"]}
    verify_b = json.loads(VERIFY_BASELINE.read_text(encoding="utf-8"))
    verify_c = json.loads(VERIFY_CANDIDATE.read_text(encoding="utf-8"))
    ratio_request = verify_c["request_tokens"] / verify_b["request_tokens"]
    ratio_embed = verify_c["payload_tokens"] / verify_b["payload_tokens"]
    gates = {
        "quality": {
            "metric": "mean recall_at_5",
            "scope": "all 223 queries",
            "value": _unrounded(cand_rows, "recall_at_5"),
            "comparator": ">=",
            "threshold": spec["quality"]["threshold"],
            "basis": spec["quality"]["basis"],
        },
        "regression": {
            "metric": "mean recall_at_10",
            "scope": "identifier-heavy queries (n=200)",
            "value": _unrounded(cand_rows, "recall_at_10", "identifier-heavy"),
            "comparator": ">=",
            "threshold": spec["regression"]["threshold"],
            "basis": spec["regression"]["basis"],
        },
        "cost": {
            "metric": "total_embedded_tokens ratio (request-text basis)",
            "scope": "full index build",
            "value": ratio_request,
            "comparator": "<=",
            "threshold": spec["cost"]["threshold_ratio_to_baseline"],
            "basis": "retrospective verify_accounting.py (TDR-022 corrected method); "
            f"candidate {verify_c['request_tokens']:,} / baseline "
            f"{verify_b['request_tokens']:,} request tokens; pre-adapter EMBED-basis "
            f"ratio {ratio_embed:.6f} also passes; committed in 8902309",
        },
        "latency": {
            "metric": "query_p95_latency_ms",
            "scope": "all 223 candidate queries",
            "value": _unrounded_p95_ms(cand_rows),
            "comparator": "<=",
            "threshold": spec["cost"]["additional"]["threshold"],
            "basis": spec["cost"]["additional"]["basis"],
        },
    }
    for gate in gates.values():
        if gate["comparator"] == ">=":
            gate["pass"] = gate["value"] >= gate["threshold"]
        else:
            gate["pass"] = gate["value"] <= gate["threshold"]
    return gates, all(g["pass"] for g in gates.values())


def main() -> None:
    """Aggregate both cells, evaluate gates, write summary JSON and results.md."""
    queries = {q["query_id"]: q for q in json.loads(GT_PATH.read_text(encoding="utf-8"))["queries"]}
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    cell_rows: dict[str, list[dict]] = {}
    for cell, ckpt in (
        ("baseline_splitter", BASELINE_CKPT),
        ("model_token_markdown", CANDIDATE_CKPT),
    ):
        state = json.loads(ckpt.read_text(encoding="utf-8"))
        cell_rows[cell] = [
            {**row, "metrics": _metrics_for_query(row["parent_ids"], queries[row["query_id"]])}
            for row in state["rows"]
        ]
        print(f"[summarise] {cell}: {len(cell_rows[cell])} queries aggregated", flush=True)

    # Port-fidelity cross-check: recomputed baseline aggregates must equal
    # Experiment 22's published summary (both rounded to 6 dp by _aggregate).
    published = json.loads(BASELINE_SUMMARY.read_text(encoding="utf-8"))["metrics_by_cell"][
        "hybrid__raw"
    ]
    recomputed = _aggregate(cell_rows["baseline_splitter"])
    for cat in ("all", "identifier-heavy", "continuity"):
        for key in ("recall_at_5", "recall_at_10", "p95_latency_ms"):
            if recomputed[cat][key] != published[cat][key]:
                raise SystemExit(
                    f"metric port drift: baseline {cat}.{key} "
                    f"{recomputed[cat][key]} != exp22 published {published[cat][key]}"
                )
    print("[summarise] baseline cross-check matches exp22 published summary", flush=True)

    gates, overall_pass = _evaluate_gates(plan, cell_rows["model_token_markdown"])
    build = json.loads(BUILD_DONE.read_text(encoding="utf-8"))
    qrels_sha = hashlib.sha256(QRELS_PATH.read_bytes()).hexdigest()
    tokenizer = build.get("tokenizer")
    summary: dict = {
        "experiment": EXP_DIR.name,
        "metrics_by_cell": {cell: _aggregate(rows) for cell, rows in cell_rows.items()},
        "gates": gates,
        "overall_verdict": "PASS" if overall_pass else "FAIL",
        "runtime_manifest": {
            "embedding_model": "qwen/qwen3-embedding-4b",
            "embedding_provider": "openrouter (cloud)",
            "embedding_dims": 2560,
            "measurement_date": "2026-09-09",
            "vector_store": "lancedb",
            "chunk_count": build.get("chunk_count"),
            "corpus_docs": {"freshstack": 10009, "continuity": 15},
            "qrels_sha256": qrels_sha,
            "latency_note": "query latency includes network round-trip to OpenRouter; "
            "measured around pipeline.search exactly as exp 22 did (no warm-up pass)",
            "index_note": "omrg production ingestion with the model-token-aware "
            "Markdown chunker (ADR-063); relevance is path-level",
            "chunker_tokenizer": tokenizer,
            "preflight_assertions": {
                "embedding.model": "qwen/qwen3-embedding-4b",
                "retrieval.hybrid": True,
                "retrieval.rerank_enabled": False,
                "chunking.resolved_splitter": (
                    f"{tokenizer['model']}@{tokenizer['revision']}"
                    if isinstance(tokenizer, dict)
                    else tokenizer
                ),
            },
        },
    }

    out_json = EXP_DIR / "output/eval_results.summary.json"
    tmp = out_json.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    tmp.replace(out_json)
    write_results_md(summary, gates, overall_pass, qrels_sha, build)
    print(f"[summarise] wrote {out_json} and results.md", flush=True)
    print(f"[summarise] overall verdict: {'PASS' if overall_pass else 'FAIL'}", flush=True)


if __name__ == "__main__":
    main()
