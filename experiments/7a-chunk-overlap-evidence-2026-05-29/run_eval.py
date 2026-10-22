"""Evidence-level evaluator for Experiment 7a — chunk overlap sensitivity.

Sweeps an arbitrary list of CHUNK_OVERLAP values across two passes
(reranker off / on) and one or more top-k values, on the Qasper-dev
corpus copied from Experiment 6b.

Reuses the metric set from 6c (Evidence Recall@K, Evidence MRR, Section
Match@1, nDCG@5/10) and the evidence-density guard.

Run with:
    cd experiments/7a-chunk-overlap-evidence-2026-05-29
    uv run python ingest_overlap.py --overlaps 32,64,100,128
    uv run python run_eval.py \\
        --overlaps 32,64,100,128 \\
        --top-ks 5,10,20 \\
        --rerank both
"""

# NOTE (v2.0.0): this script targets the PRE-v2.0.0 import surface
# (omrg.ingestion, omrg.retrieval, omrg.reranker, ...), which was
# removed by the architecture-v2 conformance change. It is an archived
# historical artefact, is not run in CI, and is intentionally NOT repaired:
# its results are already recorded in results.md, and rewriting it would
# change the code that produced them. See docs/adr/037.


from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

EXPERIMENT_DIR = Path(__file__).parent
GROUND_TRUTH_PATH = EXPERIMENT_DIR / "ground-truth.json"
CHUNK_SIZE = 512
SIZE_CAP_TOKENS = int(CHUNK_SIZE * 1.1)


@dataclass
class QueryResult:
    id: str
    query: str
    category: str
    expected_source: str
    expected_section: str | None
    evidence_snippets: list[str]
    top_k_sources: list[str] = field(default_factory=list)
    top_k_scores: list[float] = field(default_factory=list)
    top_k_texts: list[str] = field(default_factory=list)
    top_k_sections: list[str | None] = field(default_factory=list)
    relevance_grades: list[int] = field(default_factory=list)
    evidence_hit_rank: int | None = None
    source_hit_rank: int | None = None
    section_match_at_1: bool = False
    ndcg_5: float = 0.0
    ndcg_10: float = 0.0
    latency_ms: float = 0.0


@dataclass
class ChunkStats:
    total_chunks: int
    mean_token_estimate: float
    p95_token_estimate: float
    max_token_estimate: int
    over_cap_count: int
    heading_metadata_rate: float


@dataclass
class Evaluation:
    label: str
    overlap: int
    top_k: int
    rerank: bool
    chroma_dir: str
    dataset_source: str
    queries: list[QueryResult] = field(default_factory=list)
    chunk_stats: ChunkStats | None = None
    metrics_by_category: dict[str, dict[str, float]] = field(default_factory=dict)
    overall: dict[str, float] = field(default_factory=dict)
    mean_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _token_estimate(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _load_ground_truth() -> tuple[str, list[dict[str, Any]]]:
    if not GROUND_TRUTH_PATH.exists():
        raise SystemExit(f"ground-truth not found: {GROUND_TRUTH_PATH}")
    data = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    queries = data.get("queries", [])
    _validate_evidence_density(queries)
    return data.get("dataset_source", "unknown"), queries


def _validate_evidence_density(queries: list[dict[str, Any]]) -> None:
    if not queries:
        raise SystemExit("No queries found in ground-truth.json")
    evidence_labelled = [
        q for q in queries
        if q.get("evidence_ids") or q.get("evidence_snippets") or q.get("expected_answer")
    ]
    density = len(evidence_labelled) / len(queries)
    missing_source = [q.get("id", q.get("query", "?")) for q in queries if not q.get("expected_source")]
    errors = []
    if density < 0.8:
        errors.append(f"evidence density {density:.1%} < 80%")
    if missing_source:
        errors.append(f"missing expected_source for {missing_source[:5]}")
    if errors:
        raise SystemExit("Evidence-sparse evaluation set rejected: " + "; ".join(errors))


def _setup_chroma_dir(chroma_dir: str) -> None:
    os.environ["CHROMA_PERSIST_DIR"] = chroma_dir
    for mod_name in ("omrg.ingestion", "omrg.retrieval", "omrg.config"):
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, "CHROMA_PERSIST_DIR"):
            mod.CHROMA_PERSIST_DIR = chroma_dir


def _section_from_metadata(meta: dict[str, Any], text: str) -> str | None:
    for key in ("heading_path", "header", "section", "Header_1", "Header_2", "Header_3"):
        value = meta.get(key)
        if value:
            if isinstance(value, list):
                return " / ".join(str(v) for v in value)
            return str(value)
    headings = re.findall(r"(?m)^#{1,6}\s+(.+?)\s*$", text)
    return " / ".join(headings[-3:]) if headings else None


def _collect_chunk_stats(chroma_dir: str) -> ChunkStats:
    import chromadb

    client = chromadb.PersistentClient(path=chroma_dir)
    collections = client.list_collections()
    if not collections:
        return ChunkStats(0, 0.0, 0.0, 0, 0, 0.0)
    collection = collections[0]
    data = collection.get(include=["documents", "metadatas"])
    docs = data.get("documents") or []
    metas = data.get("metadatas") or []
    lengths = [_token_estimate(d or "") for d in docs]
    if not lengths:
        return ChunkStats(0, 0.0, 0.0, 0, 0, 0.0)
    sorted_lengths = sorted(lengths)
    cuts = (
        statistics.quantiles(sorted_lengths, n=100, method="inclusive")
        if len(lengths) > 1
        else [lengths[0]] * 99
    )
    heading_count = sum(
        1 for doc, meta in zip(docs, metas)
        if _section_from_metadata(meta or {}, doc or "")
    )
    return ChunkStats(
        total_chunks=len(lengths),
        mean_token_estimate=round(statistics.mean(lengths), 1),
        p95_token_estimate=round(cuts[94], 1),
        max_token_estimate=max(lengths),
        over_cap_count=sum(1 for length in lengths if length > SIZE_CAP_TOKENS),
        heading_metadata_rate=round(heading_count / len(lengths), 4),
    )


def _snippet_hit(text: str, snippets: list[str]) -> bool:
    norm_text = _norm(text)
    return any(_norm(snippet) in norm_text for snippet in snippets if snippet and _norm(snippet))


def _source_match(expected_source: str, source: str) -> bool:
    return bool(expected_source) and expected_source.lower() in source.lower()


def _section_match(expected_section: str | None, section: str | None, text: str) -> bool:
    if not expected_section:
        return False
    target = _norm(expected_section)
    return target in _norm(section or "") or target in _norm(text)


def _dcg(grades: list[int]) -> float:
    return sum((2 ** grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, start=1))


def _ndcg(grades: list[int], k: int = 5) -> float:
    actual = grades[:k]
    ideal = sorted(grades, reverse=True)[:k]
    ideal_dcg = _dcg(ideal)
    return 0.0 if ideal_dcg == 0 else _dcg(actual) / ideal_dcg


def _evaluate(
    *,
    overlap: int,
    chroma_dir: str,
    dataset_source: str,
    queries: list[dict[str, Any]],
    rerank: bool,
    top_k: int,
) -> Evaluation:
    """Run the full query set against one (overlap, top_k, rerank) cell."""
    from omrg.retrieval import search

    _setup_chroma_dir(chroma_dir)
    label = f"overlap={overlap}/top_k={top_k}/rerank={'on' if rerank else 'off'}"
    ev = Evaluation(
        label=label,
        overlap=overlap,
        top_k=top_k,
        rerank=rerank,
        chroma_dir=chroma_dir,
        dataset_source=dataset_source,
    )
    ev.chunk_stats = _collect_chunk_stats(chroma_dir)

    latencies: list[float] = []
    for qa in queries:
        snippets = list(qa.get("evidence_snippets") or [])
        if qa.get("expected_answer"):
            snippets.append(str(qa["expected_answer"]))

        started = time.perf_counter()
        results = search(qa["query"], top_k=top_k, similarity_threshold=0.0, rerank=rerank)
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)

        sources = [r.get("source", "") for r in results[:top_k]]
        scores = [r.get("score", 0.0) for r in results[:top_k]]
        texts = [r.get("text", "") for r in results[:top_k]]
        sections = [
            _section_from_metadata(r.get("metadata", {}) or {}, r.get("text", ""))
            for r in results[:top_k]
        ]

        evidence_rank = None
        source_rank = None
        grades: list[int] = []
        for rank, (source, text, section) in enumerate(zip(sources, texts, sections), start=1):
            e_hit = _snippet_hit(text, snippets)
            s_hit = _source_match(qa.get("expected_source", ""), source)
            sec_hit = _section_match(qa.get("expected_section"), section, text)
            if e_hit and evidence_rank is None:
                evidence_rank = rank
            if s_hit and source_rank is None:
                source_rank = rank
            grades.append(2 if (e_hit or sec_hit) else (1 if s_hit else 0))

        qr = QueryResult(
            id=str(qa.get("id", qa.get("query", ""))),
            query=qa["query"],
            category=qa.get("category", "general"),
            expected_source=qa.get("expected_source", ""),
            expected_section=qa.get("expected_section"),
            evidence_snippets=snippets,
            top_k_sources=sources,
            top_k_scores=scores,
            top_k_texts=texts,
            top_k_sections=sections,
            relevance_grades=grades,
            evidence_hit_rank=evidence_rank,
            source_hit_rank=source_rank,
            section_match_at_1=bool(
                texts and _section_match(qa.get("expected_section"), sections[0], texts[0])
            ),
            ndcg_5=round(_ndcg(grades, 5), 4),
            ndcg_10=round(_ndcg(grades, 10), 4),
            latency_ms=round(latency_ms, 2),
        )
        ev.queries.append(qr)

    ev.metrics_by_category = _aggregate(ev.queries)
    ev.overall = _aggregate_overall(ev.queries)
    if latencies:
        ev.mean_latency_ms = round(statistics.mean(latencies), 2)
        if len(latencies) > 1:
            cuts = statistics.quantiles(sorted(latencies), n=100, method="inclusive")
            ev.p95_latency_ms = round(cuts[94], 2)
        else:
            ev.p95_latency_ms = round(latencies[0], 2)
    return ev


def _aggregate(queries: list[QueryResult]) -> dict[str, dict[str, float]]:
    """Per-category Evidence Recall@K, MRR, Section Match@1, nDCG@5/10."""
    by_cat: dict[str, list[QueryResult]] = defaultdict(list)
    for q in queries:
        by_cat[q.category].append(q)
    metrics: dict[str, dict[str, float]] = {}
    for cat, items in by_cat.items():
        n = len(items)
        rr = [(1 / q.evidence_hit_rank) if q.evidence_hit_rank else 0.0 for q in items]
        metrics[cat] = {
            "n": n,
            "evidence_recall_at_1": round(sum(q.evidence_hit_rank == 1 for q in items) / n, 4),
            "evidence_recall_at_3": round(
                sum(q.evidence_hit_rank is not None and q.evidence_hit_rank <= 3 for q in items) / n, 4
            ),
            "evidence_recall_at_5": round(
                sum(q.evidence_hit_rank is not None and q.evidence_hit_rank <= 5 for q in items) / n, 4
            ),
            "evidence_recall_at_10": round(
                sum(q.evidence_hit_rank is not None and q.evidence_hit_rank <= 10 for q in items) / n, 4
            ),
            "evidence_mrr": round(sum(rr) / n, 4),
            "section_match_at_1": round(sum(q.section_match_at_1 for q in items) / n, 4),
            "ndcg_5": round(sum(q.ndcg_5 for q in items) / n, 4),
            "ndcg_10": round(sum(q.ndcg_10 for q in items) / n, 4),
            "source_hit_at_1_diagnostic": round(sum(q.source_hit_rank == 1 for q in items) / n, 4),
        }
    return metrics


def _aggregate_overall(queries: list[QueryResult]) -> dict[str, float]:
    """Whole-corpus aggregate (used as the primary verdict)."""
    n = len(queries)
    if n == 0:
        return {}
    rr = [(1 / q.evidence_hit_rank) if q.evidence_hit_rank else 0.0 for q in queries]
    return {
        "n": n,
        "evidence_recall_at_1": round(sum(q.evidence_hit_rank == 1 for q in queries) / n, 4),
        "evidence_recall_at_3": round(
            sum(q.evidence_hit_rank is not None and q.evidence_hit_rank <= 3 for q in queries) / n, 4
        ),
        "evidence_recall_at_5": round(
            sum(q.evidence_hit_rank is not None and q.evidence_hit_rank <= 5 for q in queries) / n, 4
        ),
        "evidence_recall_at_10": round(
            sum(q.evidence_hit_rank is not None and q.evidence_hit_rank <= 10 for q in queries) / n, 4
        ),
        "evidence_mrr": round(sum(rr) / n, 4),
        "ndcg_5": round(sum(q.ndcg_5 for q in queries) / n, 4),
        "ndcg_10": round(sum(q.ndcg_10 for q in queries) / n, 4),
    }


def _print_table(evaluations: list[Evaluation]) -> None:
    """Compact comparison table across the sweep."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Experiment 7a — Chunk Overlap Sensitivity (Qasper-dev evidence-level)")
        table.add_column("Overlap", justify="right")
        table.add_column("top_k", justify="right")
        table.add_column("Pass", justify="center")
        table.add_column("Recall@1", justify="right")
        table.add_column("Recall@5", justify="right")
        table.add_column("Recall@10", justify="right")
        table.add_column("MRR", justify="right")
        table.add_column("nDCG@5", justify="right")
        table.add_column("Sec@1", justify="right")
        table.add_column("Chunks", justify="right")
        table.add_column("P95 ms", justify="right")
        for ev in evaluations:
            o = ev.overall
            cs = ev.chunk_stats
            table.add_row(
                str(ev.overlap),
                str(ev.top_k),
                "B" if ev.rerank else "A",
                f"{100 * o.get('evidence_recall_at_1', 0):.1f}%",
                f"{100 * o.get('evidence_recall_at_5', 0):.1f}%",
                f"{100 * o.get('evidence_recall_at_10', 0):.1f}%",
                f"{o.get('evidence_mrr', 0):.3f}",
                f"{o.get('ndcg_5', 0):.3f}",
                f"{100 * sum(q.section_match_at_1 for q in ev.queries) / max(len(ev.queries), 1):.1f}%",
                str(cs.total_chunks if cs else 0),
                f"{ev.p95_latency_ms:.0f}",
            )
        console.print()
        console.print(table)
        console.print()
    except ImportError:
        for ev in evaluations:
            o = ev.overall
            print(
                f"  overlap={ev.overlap:>3} top_k={ev.top_k:>2} "
                f"pass={'B' if ev.rerank else 'A'} "
                f"R@5={100*o.get('evidence_recall_at_5', 0):>5.1f}% "
                f"MRR={o.get('evidence_mrr', 0):.3f} "
                f"chunks={ev.chunk_stats.total_chunks if ev.chunk_stats else 0}"
            )


def _check_pass_criteria(evaluations: list[Evaluation]) -> dict[str, Any]:
    """Compute the headline non-regression and storage criteria.

    Anchors on overlap=64 (the previous default) at the lowest top_k cell.
    For each non-anchor (overlap, pass, top_k) combination, records whether
    Evidence Recall@5 and MRR are non-regressions vs the anchor at the same
    (pass, top_k) cell.  Records the chunk-count delta for storage.
    """
    by_key: dict[tuple[int, bool, int], Evaluation] = {
        (ev.overlap, ev.rerank, ev.top_k): ev for ev in evaluations
    }
    overlaps = sorted({ev.overlap for ev in evaluations})
    passes = sorted({ev.rerank for ev in evaluations})
    top_ks = sorted({ev.top_k for ev in evaluations})

    anchor = 64
    results: dict[str, Any] = {
        "anchor_overlap": anchor,
        "overlaps": overlaps,
        "passes": ["A (rerank off)", "B (rerank on)"][:len(passes)],
        "top_ks": top_ks,
        "cells": [],
    }
    for rerank in passes:
        for top_k in top_ks:
            base = by_key.get((anchor, rerank, top_k))
            if base is None:
                continue
            for overlap in overlaps:
                cand = by_key.get((overlap, rerank, top_k))
                if cand is None or overlap == anchor:
                    continue
                base_recall = base.overall.get("evidence_recall_at_5", 0.0)
                cand_recall = cand.overall.get("evidence_recall_at_5", 0.0)
                base_mrr = base.overall.get("evidence_mrr", 0.0)
                cand_mrr = cand.overall.get("evidence_mrr", 0.0)
                base_chunks = base.chunk_stats.total_chunks if base.chunk_stats else 0
                cand_chunks = cand.chunk_stats.total_chunks if cand.chunk_stats else 0
                results["cells"].append({
                    "overlap": overlap,
                    "anchor": anchor,
                    "pass": "B" if rerank else "A",
                    "top_k": top_k,
                    "evidence_recall_at_5_anchor": base_recall,
                    "evidence_recall_at_5_candidate": cand_recall,
                    "evidence_recall_at_5_delta_pp": round(100 * (cand_recall - base_recall), 2),
                    "evidence_recall_at_5_non_regression_pass": (cand_recall - base_recall) >= -0.02,
                    "mrr_delta": round(cand_mrr - base_mrr, 4),
                    "mrr_non_regression_pass": (cand_mrr - base_mrr) >= -0.01,
                    "chunk_count_anchor": base_chunks,
                    "chunk_count_candidate": cand_chunks,
                    "chunk_count_ratio": round(cand_chunks / max(base_chunks, 1), 3),
                    "chunk_count_within_15pct_pass": cand_chunks <= base_chunks * 1.15,
                })
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--overlaps",
        type=str,
        default="32,64,100,128",
        help="Comma-separated overlap values to evaluate.",
    )
    parser.add_argument(
        "--top-ks",
        type=str,
        default="5,10,20",
        help="Comma-separated top-k values to evaluate.",
    )
    parser.add_argument(
        "--rerank",
        choices=("off", "on", "both"),
        default="both",
        help="off = Pass A only; on = Pass B only; both = Pass A then Pass B.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=EXPERIMENT_DIR / "eval_results.json",
        help="Output JSON path.",
    )
    args = parser.parse_args()

    overlaps = [int(x) for x in args.overlaps.split(",") if x.strip()]
    top_ks = [int(x) for x in args.top_ks.split(",") if x.strip()]
    if args.rerank == "off":
        passes = [False]
    elif args.rerank == "on":
        passes = [True]
    else:
        passes = [False, True]

    dataset_source, queries = _load_ground_truth()
    print("Experiment 7a: Chunk Overlap Sensitivity (evidence-level, Qasper-dev)")
    print(f"  Dataset source: {dataset_source}")
    print(f"  Queries: {len(queries)}")
    print(f"  Overlaps: {overlaps}")
    print(f"  Top-Ks: {top_ks}")
    print(f"  Passes: {[('A' if not p else 'B') for p in passes]}")

    # Validate that all required ChromaDB indexes exist before running.
    missing = []
    for overlap in overlaps:
        chroma_dir = (EXPERIMENT_DIR / f"chroma_overlap_{overlap}").resolve()
        if not chroma_dir.exists():
            missing.append(str(chroma_dir))
    if missing:
        raise SystemExit(
            "Missing ChromaDB indexes: " + ", ".join(missing) +
            "\nBuild them first with: uv run python ingest_overlap.py --overlaps "
            + ",".join(str(o) for o in overlaps)
        )

    evaluations: list[Evaluation] = []
    for overlap in overlaps:
        chroma_dir = str((EXPERIMENT_DIR / f"chroma_overlap_{overlap}").resolve())
        for rerank in passes:
            for top_k in top_ks:
                # Reset reranker singleton between cells so each cell starts
                # from a clean cross-encoder state.
                try:
                    from omrg.reranker import CrossEncoderReranker
                    CrossEncoderReranker._instance = None  # type: ignore[attr-defined]
                except Exception:
                    pass
                ev = _evaluate(
                    overlap=overlap,
                    chroma_dir=chroma_dir,
                    dataset_source=dataset_source,
                    queries=queries,
                    rerank=rerank,
                    top_k=top_k,
                )
                evaluations.append(ev)
                o = ev.overall
                print(
                    f"  [overlap={overlap:>3} pass={'B' if rerank else 'A'} top_k={top_k:>2}] "
                    f"R@5={100 * o.get('evidence_recall_at_5', 0):>5.1f}%  "
                    f"MRR={o.get('evidence_mrr', 0):.3f}  "
                    f"P95={ev.p95_latency_ms:.0f}ms"
                )

    _print_table(evaluations)
    criteria = _check_pass_criteria(evaluations)
    print("\nPass Criteria (vs overlap=64 anchor at the same pass / top_k cell)")
    print("-" * 70)
    for cell in criteria["cells"]:
        print(
            f"  overlap={cell['overlap']:>3} pass={cell['pass']} top_k={cell['top_k']:>2}  "
            f"ΔR@5={cell['evidence_recall_at_5_delta_pp']:>+6.2f}pp  "
            f"chunks={cell['chunk_count_ratio']}× "
            f"non-regression={cell['evidence_recall_at_5_non_regression_pass']}"
        )

    args.out.write_text(
        json.dumps(
            {
                "experiment": "7a-chunk-overlap-evidence",
                "dataset_source": dataset_source,
                "overlaps": overlaps,
                "top_ks": top_ks,
                "passes": [("A" if not p else "B") for p in passes],
                "evaluations": [asdict(ev) for ev in evaluations],
                "pass_criteria": criteria,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nRaw results saved to: {args.out}")


if __name__ == "__main__":
    main()
