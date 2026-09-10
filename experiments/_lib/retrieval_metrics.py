"""Shared retrieval metrics, verbatim port from Experiment 22's summariser.

``rank_map``, ``alpha_ndcg``, ``metrics_for_query`` and ``aggregate``
were ported from Experiment 22 (itself ported from 9a) so every cell is
scored by identical code and the numbers stay comparable with the
baseline. Do not modify them. Experiments 26 and 27 import these so
their summarisers stay under the file-size budget without diverging.
"""

from __future__ import annotations

import math
import statistics

K_VALUES = (1, 3, 5, 10, 20, 50)


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
