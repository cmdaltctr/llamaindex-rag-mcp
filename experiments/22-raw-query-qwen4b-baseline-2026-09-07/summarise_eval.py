"""Experiment 22 summariser: aggregate both cells into metrics + results.md.

Metric definitions are ported verbatim from experiment 9a's runner
(``_rank_map``, ``_alpha_ndcg``, ``_metrics_for_query``) so the numbers
stay comparable, extended with the recall@{1,3,5} task 1.5 requires.

Writes:
- output/eval_results.summary.json  (per cell × category aggregates)
- results.md                        (tables + runtime manifest block)
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
GT_PATH = EXP_DIR / "output/ground-truth.json"
QRELS_PATH = EXP_DIR / "output/freshstack-qrels.json"
CELLS = ("dense_only__raw", "hybrid__raw")
K_VALUES = (1, 3, 5, 10, 20, 50)
CELL_NAMES = {
    "dense_only__raw": "dense-only",
    "hybrid__raw": "hybrid (BM25 + dense, RRF)",
}
CAT_ORDER = ("all", "identifier-heavy", "semantic", "continuity")
CAT_TITLES = {
    "all": "All queries",
    "identifier-heavy": "Identifier-heavy queries",
    "semantic": "Semantic queries",
    "continuity": "Continuity queries",
}
# (json key, table header, direction) — "up" = higher is better,
# "down" = lower is better (latency). Drives formatting and bolding.
TABLE_COLS = (
    ("recall_at_1", "R@1", "up"),
    ("recall_at_3", "R@3", "up"),
    ("recall_at_5", "R@5", "up"),
    ("recall_at_10", "R@10", "up"),
    ("recall_at_50", "R@50", "up"),
    ("coverage_at_20", "Coverage@20", "up"),
    ("alpha_ndcg_at_10", "α-nDCG@10", "up"),
    ("hit_at_10", "Hit@10", "up"),
    ("mrr_at_10", "MRR@10", "up"),
    ("mean_latency_ms", "Mean latency", "down"),
    ("p95_latency_ms", "P95 latency", "down"),
)


def _pct(value: float) -> str:
    """Format a 0..1 metric as a percentage string."""
    return f"{value * 100:.1f}%"


def _ms(value: float) -> str:
    """Format a millisecond figure with thousands separators."""
    return f"{value:,.0f} ms"


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


def main() -> None:
    """Aggregate both cells, write summary JSON and results.md."""
    queries = {q["query_id"]: q for q in json.loads(GT_PATH.read_text(encoding="utf-8"))["queries"]}
    summary: dict = {"experiment": EXP_DIR.name, "metrics_by_cell": {}}

    first_rank: dict[str, dict[str, int | None]] = {c: {} for c in CELLS}
    for cell in CELLS:
        path = EXP_DIR / "output/cells" / f"{cell}.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        rows = []
        for row in state["rows"]:
            query = queries[row["query_id"]]
            metrics = _metrics_for_query(row["parent_ids"], query)
            first_rank[cell][row["query_id"]] = metrics["first_relevant_rank"]
            rows.append({**row, "metrics": metrics})
        summary["metrics_by_cell"][cell] = _aggregate(rows)
        print(f"[summarise] {cell}: {len(rows)} queries aggregated", flush=True)

    qrels_sha = hashlib.sha256(QRELS_PATH.read_bytes()).hexdigest()
    build = json.loads((EXP_DIR / "output/build_done.json").read_text(encoding="utf-8"))
    summary["runtime_manifest"] = {
        "embedding_model": "qwen/qwen3-embedding-4b",
        "embedding_provider": "openrouter (cloud)",
        "embedding_dims": 2560,
        "digest_note": "cloud inference cannot pin a model digest; slug + date recorded",
        "measurement_date": "2026-09-07",
        "vector_store": "lancedb",
        "chunk_count": build.get("chunk_count"),
        "corpus_docs": {"freshstack": 10009, "continuity": 15},
        "qrels_sha256": qrels_sha,
        "latency_note": "query latency includes network round-trip to OpenRouter",
        "index_note": "omrg production ingestion (default chunking); relevance is "
        "path-level, not char-offset-level",
    }

    out_json = EXP_DIR / "output/eval_results.summary.json"
    tmp = out_json.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    tmp.replace(out_json)

    # ---------------------------------------------------------------
    # results.md — house presentation convention (experiments 9a / 21)
    # ---------------------------------------------------------------
    by_cell = summary["metrics_by_cell"]
    d, h = by_cell["dense_only__raw"], by_cell["hybrid__raw"]
    d_all, h_all = d["all"], h["all"]

    def pp(key: str) -> str:
        """Signed percentage-point delta, hybrid minus dense."""
        return f"{(h_all[key] - d_all[key]) * 100:+.1f} pp"

    def cat_table(cat: str, bold: bool) -> list[str]:
        headers = [hdr for _, hdr, _ in TABLE_COLS]
        winner: dict[str, str] = {}
        if bold:
            for key, _, direction in TABLE_COLS:
                dv, hv = d[cat][key], h[cat][key]
                if direction == "up":
                    better = "hybrid__raw" if hv > dv else "dense_only__raw" if dv > hv else ""
                else:
                    better = "hybrid__raw" if hv < dv else "dense_only__raw" if dv < hv else ""
                if better:
                    winner[key] = better
        out = [
            "| Cell | " + " | ".join(headers) + " |",
            "| --- | " + " | ".join(["---:"] * len(headers)) + " |",
        ]
        for cell in CELLS:
            agg = by_cell[cell][cat]
            row = [CELL_NAMES[cell]]
            for key, _, direction in TABLE_COLS:
                text = _ms(agg[key]) if direction == "down" else _pct(agg[key])
                if winner.get(key) == cell:
                    text = f"**{text}**"
                row.append(text)
            out.append("| " + " | ".join(row) + " |")
        return out

    lines = [
        "# Experiment 22 Results: Raw-Query Qwen3-Embedding-4B Retrieval Baseline",
        "",
        "**ID**: `22-raw-query-qwen4b-baseline-2026-09-07`  ",
        "**Date completed**: 2026-09-07  ",
        "**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent  ",
        "**Status**: COMPLETE — measurement run. No pass/fail gates; task 1.6 "
        "derives the frozen regression and latency gates from these numbers.  ",
        "**Raw data**: [`output/eval_results.summary.json`](./output/eval_results.summary.json)",
        "",
        "---",
        "",
        "## Executive summary",
        "",
        "This experiment recorded the retrieval baseline for the raw query path "
        "under the embedding model this change targets: "
        "`qwen/qwen3-embedding-4b` served via OpenRouter (EMBED_PROVIDER=cloud), "
        "stored in LanceDB. Two arms ran over the identical FreshStack LangChain "
        "corpus and qrels as Experiment 9a (10,024 parent documents, 223 "
        "queries): dense-only and hybrid (BM25 + dense with RRF fusion), both "
        "without reranking.",
        "",
        f"**Bottom line**: hybrid leads on every headline quality metric except "
        f"Recall@1, where dense-only keeps a small edge ({_pct(d_all['recall_at_1'])} "
        f"vs {_pct(h_all['recall_at_1'])}). On the primary metric, Recall@5, hybrid "
        f"scores {_pct(h_all['recall_at_5'])} against dense-only's "
        f"{_pct(d_all['recall_at_5'])} ({pp('recall_at_5')}). Hybrid is also "
        f"quicker at the tail (P95 {_ms(h_all['p95_latency_ms'])} vs "
        f"{_ms(d_all['p95_latency_ms'])}), though both arms include the "
        "OpenRouter network round-trip in every latency figure.",
        "",
        "These numbers are the frozen reference for every Stage 5 candidate "
        "(query instruction, model-token-aware chunking, OCR routing). They are "
        "NOT comparable with Experiment 9a's local `qwen3-embedding:0.6b` cells: "
        "different model, embedding width (2560 vs 1024), vector store, and "
        "ingestion granularity. The shared qrels anchor corpus identity only.",
        "",
        "## Corpus and setup",
        "",
        "| Parameter | Value |",
        "| --- | --- |",
        "| Corpus source | FreshStack LangChain, October 2024 (9a re-export, `prepare_freshstack.py`, seed 20260530) |",
        "| Parent documents indexed | 10,024 (10,009 FreshStack + 15 continuity) |",
        f"| Chunks stored | {build.get('chunk_count'):,} (omrg production ingestion, default chunking) |",
        "| Query set | 203 FreshStack test queries + 20 continuity queries = 223 total |",
        "| Query categories | 200 identifier-heavy, 3 semantic, 20 continuity |",
        "| Query path | raw (no instruction template) |",
        "| Embedding model | `qwen/qwen3-embedding-4b` via OpenRouter (cloud) |",
        "| Embedding width | 2560 |",
        "| Vector store | LanceDB (one row per chunk, parent-level relevance) |",
        "| Fusion | RRF, k = 60 (production default `hybrid_rrf_k`) |",
        "| Reranking | disabled (`RETRIEVAL__RERANK_ENABLED=false`, packaged default) |",
        "| Fetch depth | top_k = 50 |",
        f"| Qrels sha256 | `{qrels_sha[:16]}…` (identical to 9a) |",
        f"| Index build time | ~{build.get('elapsed_s', 0) / 3600:.1f} h (cloud embeddings) |",
        "",
        "## Cell metrics",
        "",
    ]

    for cat in CAT_ORDER:
        agg = by_cell["dense_only__raw"][cat]
        lines += [
            f"### {CAT_TITLES[cat]} (n = {agg['n']})",
            "",
            *cat_table(cat, bold=(cat != "semantic")),
            "",
        ]
        if cat == "all":
            lines += [
                "*Cell = retrieval arm tested; R@K = recall at cutoff K, the "
                "percentage of each query's ground-truth relevant parent documents "
                "found in the top K results; Coverage@20 = mean fraction of a "
                "query's nuggets (sub-questions) covered by the top-20 results; "
                "α-nDCG@10 = alpha-normalised Discounted Cumulative Gain at 10, "
                "which rewards covering multiple relevant nuggets at high ranks "
                "(1.0 = perfect ranking); Hit@10 = percentage of queries with at "
                "least one relevant document in the top 10; MRR@10 = Mean "
                "Reciprocal Rank at 10, the average of 1/rank for the first "
                "relevant result (1.0 = always rank 1); Mean/P95 latency = "
                "average and 95th-percentile query time, both including the "
                "OpenRouter network round-trip; RRF = Reciprocal Rank Fusion, "
                "the algorithm that merges dense and BM25 rank lists; BM25 = Best "
                "Matching 25, a keyword-frequency retrieval algorithm. Bold marks "
                "the better arm per metric.*",
                "",
            ]
        else:
            lines += ["*Metric definitions as in the all-queries table.*", ""]
        if cat == "semantic":
            lines += ["*Note: only 3 semantic queries — too few for statistical conclusions.*", ""]

    lines += [
        "## Arm comparison (all queries)",
        "",
        "| Metric | Dense-only | Hybrid | Δ (hybrid − dense) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key, label in (
        ("recall_at_1", "Recall@1"),
        ("recall_at_5", "Recall@5"),
        ("recall_at_10", "Recall@10"),
        ("recall_at_50", "Recall@50"),
        ("coverage_at_20", "Coverage@20"),
        ("alpha_ndcg_at_10", "α-nDCG@10"),
        ("hit_at_10", "Hit@10"),
        ("mrr_at_10", "MRR@10"),
    ):
        lines.append(f"| {label} | {_pct(d_all[key])} | {_pct(h_all[key])} | {pp(key)} |")
    lines.append(
        f"| Mean latency | {_ms(d_all['mean_latency_ms'])} | {_ms(h_all['mean_latency_ms'])} | "
        f"{h_all['mean_latency_ms'] - d_all['mean_latency_ms']:+,.0f} ms |"
    )
    lines.append(
        f"| P95 latency | {_ms(d_all['p95_latency_ms'])} | {_ms(h_all['p95_latency_ms'])} | "
        f"{h_all['p95_latency_ms'] - d_all['p95_latency_ms']:+,.0f} ms |"
    )

    # Task 1.5 evidence: representative identifier-heavy queries — the
    # three largest hybrid rescues and two largest dense-only advantages,
    # selected by first-relevant-rank difference between arms.
    def _rank_text(cell: str, qid: str) -> str:
        r = first_rank[cell].get(qid)
        return "—" if r is None else str(r)

    scored: list[tuple[int, str]] = []
    for qid, q in queries.items():
        if q["category"] != "identifier-heavy":
            continue
        dr = first_rank["dense_only__raw"].get(qid)
        hr = first_rank["hybrid__raw"].get(qid)
        if dr is None and hr is None:
            continue
        scored.append(((hr if hr is not None else 10**9) - (dr if dr is not None else 10**9), qid))
    scored.sort()
    rescued = scored[:3]
    dense_wins = sorted(scored, key=lambda t: -t[0])[:2]

    def _rep_table(entries: list[tuple[int, str]]) -> list[str]:
        out = [
            "| Query | Title | Dense rank | Hybrid rank |",
            "| --- | --- | ---: | ---: |",
        ]
        for _, qid in entries:
            title = queries[qid]["query_title"].replace("|", "\\|")
            if len(title) > 60:
                title = title[:57] + "…"
            out.append(
                f"| `{qid}` | {title} | {_rank_text('dense_only__raw', qid)} | "
                f"{_rank_text('hybrid__raw', qid)} |"
            )
        return out

    lines += [
        "",
        "## Representative identifier-heavy queries",
        "",
        "### Largest hybrid rescues",
        "",
        *_rep_table(rescued),
        "",
        "### Largest dense-only advantages",
        "",
        *_rep_table(dense_wins),
        "",
        "*Rank = position of the first relevant parent in that arm's top-50 "
        "results; “—” = no relevant parent retrieved in the top 50. Selected "
        "from the 200 identifier-heavy queries by first-relevant-rank "
        "difference between arms.*",
    ]

    lines += [
        "",
        "## Observations",
        "",
        f"1. Hybrid leads dense-only on every headline quality metric except "
        f"Recall@1 ({_pct(d_all['recall_at_1'])} vs {_pct(h_all['recall_at_1'])}, "
        f"{pp('recall_at_1')}).",
        f"2. The hybrid advantage widens with cutoff depth on the recall family: "
        f"R@5 {pp('recall_at_5')}, R@10 {pp('recall_at_10')}, R@50 {pp('recall_at_50')}.",
        f"3. Latency: hybrid mean {_ms(h_all['mean_latency_ms'])} vs dense "
        f"{_ms(d_all['mean_latency_ms'])}; P95 {_ms(h_all['p95_latency_ms'])} vs "
        f"{_ms(d_all['p95_latency_ms'])}. Every query in both arms is embedded "
        "through OpenRouter, so both carry the network round-trip.",
        "4. The semantic category holds 3 queries — no statistical conclusions.",
        f"5. Continuity queries (n = 20) score near ceiling for both arms "
        f"(Recall@1 {_pct(d['continuity']['recall_at_1'])} dense vs "
        f"{_pct(h['continuity']['recall_at_1'])} hybrid), matching the 9a pattern.",
        "",
        "## Interpretation",
        "",
        "### Why hybrid gains concentrate below the top rank",
        "",
        "The corpus is dominated by identifier-heavy queries (200 of 223). For "
        "these, BM25 supplies exact-token evidence that dense similarity ranks "
        "mid-list, and RRF fusion promotes such parents into the 5–50 window. "
        "This reproduces, under the 4B cloud model, the first-stage hybrid "
        "advantage 9a measured with the local 0.6B model.",
        "",
        "### Why dense-only keeps Recall@1",
        "",
        f"RRF (k = 60) mixes two rank lists, so a strong dense top-1 parent can "
        f"be demoted when BM25 ordering disagrees. Dense-only converts "
        f"{_pct(d_all['recall_at_1'])} of queries at rank 1 against hybrid's "
        f"{_pct(h_all['recall_at_1'])} — the known cost of fusion at the very "
        "top. The Stage 5 instruction-template candidates may shift this "
        "balance.",
        "",
        "### Latency is cloud-inclusive",
        "",
        "Every timed query embeds through OpenRouter, so the mean and P95 "
        "figures bundle network round-trips with local retrieval. The dense "
        "arm's P95 tail reflects network variance rather than algorithmic cost; "
        "BM25 runs locally. Task 1.6 should treat absolute latency as "
        "cloud-inclusive upper bounds and freeze gates on the relative gap.",
        "",
        "### Not comparable with Experiment 9a",
        "",
        "Model (4B cloud vs 0.6B local), embedding width (2560 vs 1024), vector "
        "store (LanceDB vs ChromaDB), and ingestion granularity (32,631 "
        "production chunks vs 9a's parent-per-vector helper) all differ. The "
        "qrels sha anchors corpus identity only; metric values are this "
        "change's standalone baseline.",
        "",
        "## Next steps",
        "",
        "1. Task 1.6: freeze the regression and latency gates from the "
        "`hybrid__raw` (production shape) numbers in this report.",
        "2. Stage 5 candidates — query instruction template, model-token-aware "
        "chunking, OCR routing — measure against the frozen gates on this "
        "corpus and qrels.",
        "3. Watch Recall@1 under fusion when evaluating instruction templates.",
        "",
        "## Reproduction",
        "",
        "```bash",
        "# Index build (complete; index preserved outside git)",
        "uv run python build_index.py",
        "",
        "# Evaluation cells (checkpoint/resume; isolated cache per arm)",
        "uv run python run_eval.py --cell dense_only__raw",
        "uv run python run_eval.py --cell hybrid__raw",
        "",
        "# Aggregates + this report",
        "uv run python summarise_eval.py",
        "```",
        "",
        "The preserved index and corpus live outside the repository — see "
        "[`DATA_LOCATIONS.md`](./DATA_LOCATIONS.md). Point `STORE_URI` at the "
        "preserved index to rerun cells without rebuilding.",
        "",
        "## Artefacts",
        "",
        "| File | Description |",
        "| --- | --- |",
        "| `protocol.md` | Pre-run plan and measurement intent |",
        "| `plan.json` | Machine-readable plan and preflight assertions |",
        "| `build_index.py` | LanceDB index builder (production ingestion) |",
        "| `run_eval.py` | Per-cell evaluation runner with checkpoint/resume |",
        "| `summarise_eval.py` | Aggregator; regenerates this report |",
        "| `DATA_LOCATIONS.md` | Preserved index and corpus locations |",
        "| `output/eval_results.summary.json` | Machine-readable aggregates and runtime manifest |",
        "| `output/cells/*.json` | Per-query checkpoints (raw retrieved parents) |",
        "| `output/build_done.json` | Index build record |",
        "",
        "---",
        "",
        "*Raw metrics: `output/eval_results.summary.json`*  ",
        "*Per-query checkpoints: `output/cells/*.json`*  ",
        "*Preserved index and corpus: [`DATA_LOCATIONS.md`](./DATA_LOCATIONS.md)*",
    ]
    (EXP_DIR / "results.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[summarise] wrote {out_json} and results.md", flush=True)


if __name__ == "__main__":
    main()
