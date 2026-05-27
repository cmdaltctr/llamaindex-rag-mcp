"""Markdown-aware chunking quality experiment.

Compares retrieval quality between two chunkers on a Markdown corpus:

  - baseline: SentenceSplitter only
  - candidate: MarkdownNodeParser → SentenceSplitter (chained, with size cap)

Reranker is disabled to isolate the chunker effect. Two ChromaDB directories
are populated separately (one per chunker) and the same query set runs against
both. Per-category Hit@1 / Hit@3 / Hit@5 / MRR are reported.

Run with:
    cd experiments/6-markdown-chunking-quality-2026-05-27
    uv run python run_eval.py \\
        --baseline-dir ./chroma_md_baseline \\
        --candidate-dir ./chroma_md_new

Both ChromaDB directories must already be populated by separate ingest runs
(see protocol.md Step 3). The script reads them and runs queries.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Ensure project source is importable.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

EXPERIMENT_DIR = Path(__file__).parent
GROUND_TRUTH_PATH = EXPERIMENT_DIR / "ground-truth.json"

# Chunk-length cap. Per design: chunk size 512, allow up to 10 % overrun.
CHUNK_SIZE = 512
SIZE_CAP = int(CHUNK_SIZE * 1.1)


@dataclass
class QueryResult:
    """Per-query result for one chunker config."""

    query: str
    expected_source: str
    expected_section: str | None
    category: str
    top_k_sources: list[str] = field(default_factory=list)
    top_k_scores: list[float] = field(default_factory=list)
    top_section: str | None = None
    hit_rank: int | None = None
    hit_at_1: bool = False
    hit_at_3: bool = False
    hit_at_5: bool = False
    section_match: bool = False
    latency_ms: float = 0.0


@dataclass
class ChunkStats:
    """ChromaDB chunk-length statistics."""

    total_chunks: int
    mean_length: float
    p95_length: float
    max_length: int
    over_cap_count: int  # chunks longer than SIZE_CAP


@dataclass
class ChunkerEvaluation:
    """Aggregate evaluation for one chunker config."""

    label: str
    chroma_dir: str
    queries: list[QueryResult] = field(default_factory=list)
    chunk_stats: ChunkStats | None = None
    # Per-category aggregates.
    metrics_by_category: dict[str, dict[str, float]] = field(default_factory=dict)


def _load_ground_truth() -> list[dict]:
    """Load the partitioned query set."""
    if not GROUND_TRUTH_PATH.exists():
        print(f"  ERROR: ground-truth not found: {GROUND_TRUTH_PATH}")
        print("  Write ~18-24 queries with category in {heading-targeted, general, cross-domain}")
        sys.exit(1)
    with open(GROUND_TRUTH_PATH) as f:
        data = json.load(f)
    queries = data.get("queries", [])
    if not queries:
        print("  ERROR: no queries in ground-truth.json")
        sys.exit(1)
    return queries


def _setup_chroma_dir(chroma_dir: str) -> None:
    """Point retrieval at the given ChromaDB directory."""
    os.environ["CHROMA_PERSIST_DIR"] = chroma_dir
    for mod_name in ("rag_mcp.ingestion", "rag_mcp.retrieval", "rag_mcp.config"):
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, "CHROMA_PERSIST_DIR"):
            mod.CHROMA_PERSIST_DIR = chroma_dir


def _collect_chunk_stats(chroma_dir: str) -> ChunkStats:
    """Read all chunks from ChromaDB and compute length statistics."""
    import statistics

    import chromadb

    client = chromadb.PersistentClient(path=chroma_dir)
    collections = client.list_collections()
    if not collections:
        return ChunkStats(0, 0.0, 0.0, 0, 0)

    collection = collections[0]
    everything = collection.get(include=["documents"])
    documents = everything.get("documents") or []
    lengths = [len(d) for d in documents]
    if not lengths:
        return ChunkStats(0, 0.0, 0.0, 0, 0)

    sorted_lengths = sorted(lengths)
    cuts = statistics.quantiles(sorted_lengths, n=100, method="inclusive")
    return ChunkStats(
        total_chunks=len(lengths),
        mean_length=round(statistics.mean(lengths), 1),
        p95_length=round(cuts[94], 1),
        max_length=max(lengths),
        over_cap_count=sum(1 for length in lengths if length > SIZE_CAP),
    )


def _evaluate_chunker(label: str, chroma_dir: str, queries: list[dict]) -> ChunkerEvaluation:
    """Run all queries against one ChromaDB directory."""
    from rag_mcp.retrieval import search

    _setup_chroma_dir(chroma_dir)
    eval_result = ChunkerEvaluation(label=label, chroma_dir=chroma_dir)
    eval_result.chunk_stats = _collect_chunk_stats(chroma_dir)

    for qa in queries:
        query_text = qa["query"]
        expected_source = qa["expected_source"]
        expected_section = qa.get("expected_section")
        category = qa.get("category", "general")

        started = time.perf_counter()
        results = search(
            query=query_text,
            top_k=5,
            similarity_threshold=0.0,
            rerank=False,  # isolate chunker effect
        )
        latency_ms = (time.perf_counter() - started) * 1000

        top_sources = [r.get("source", "") for r in results[:5]]
        top_scores = [r.get("score", 0.0) for r in results[:5]]
        top_metadata = results[0].get("metadata", {}) if results else {}
        top_section = top_metadata.get("heading_path") or top_metadata.get("header")

        hit_rank = None
        for rank, source in enumerate(top_sources, start=1):
            if expected_source.lower() in source.lower():
                hit_rank = rank
                break

        section_match = False
        if expected_section and top_section:
            section_match = expected_section.lower() in str(top_section).lower()

        eval_result.queries.append(
            QueryResult(
                query=query_text,
                expected_source=expected_source,
                expected_section=expected_section,
                category=category,
                top_k_sources=top_sources,
                top_k_scores=top_scores,
                top_section=top_section,
                hit_rank=hit_rank,
                hit_at_1=(hit_rank is not None and hit_rank <= 1),
                hit_at_3=(hit_rank is not None and hit_rank <= 3),
                hit_at_5=(hit_rank is not None and hit_rank <= 5),
                section_match=section_match,
                latency_ms=round(latency_ms, 2),
            )
        )

    eval_result.metrics_by_category = _aggregate_by_category(eval_result.queries)
    return eval_result


def _aggregate_by_category(queries: list[QueryResult]) -> dict[str, dict[str, float]]:
    """Group queries by category and compute Hit@K / MRR per group."""
    by_cat: dict[str, list[QueryResult]] = defaultdict(list)
    for q in queries:
        by_cat[q.category].append(q)

    metrics: dict[str, dict[str, float]] = {}
    for cat, items in by_cat.items():
        n = len(items)
        if n == 0:
            continue
        hit1 = sum(1 for q in items if q.hit_at_1) / n
        hit3 = sum(1 for q in items if q.hit_at_3) / n
        hit5 = sum(1 for q in items if q.hit_at_5) / n
        rr = [(1.0 / q.hit_rank) if q.hit_rank else 0.0 for q in items]
        mrr = sum(rr) / n
        metrics[cat] = {
            "n": n,
            "hit_at_1": round(hit1, 4),
            "hit_at_3": round(hit3, 4),
            "hit_at_5": round(hit5, 4),
            "mrr": round(mrr, 4),
        }
    return metrics


def _print_comparison(baseline: ChunkerEvaluation, candidate: ChunkerEvaluation) -> None:
    """Print per-category comparison and chunk-length stats."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Markdown Chunker Comparison")
        table.add_column("Config / Category")
        table.add_column("n", justify="right")
        table.add_column("Hit@1", justify="right")
        table.add_column("Hit@3", justify="right")
        table.add_column("Hit@5", justify="right")
        table.add_column("MRR", justify="right")

        for ev in (baseline, candidate):
            for cat, m in ev.metrics_by_category.items():
                table.add_row(
                    f"{ev.label} / {cat}",
                    str(int(m["n"])),
                    f"{100 * m['hit_at_1']:.1f}%",
                    f"{100 * m['hit_at_3']:.1f}%",
                    f"{100 * m['hit_at_5']:.1f}%",
                    f"{m['mrr']:.3f}",
                )

        console.print(table)
        console.print()

        for ev in (baseline, candidate):
            cs = ev.chunk_stats
            if cs is None:
                continue
            console.print(
                f"  {ev.label}: total={cs.total_chunks}  "
                f"mean={cs.mean_length}  P95={cs.p95_length}  "
                f"max={cs.max_length}  over_cap={cs.over_cap_count}"
            )
    except ImportError:
        for ev in (baseline, candidate):
            print(f"\n  {ev.label}")
            for cat, m in ev.metrics_by_category.items():
                print(
                    f"    {cat:<22} n={int(m['n'])} "
                    f"hit@1={100*m['hit_at_1']:.1f}% "
                    f"mrr={m['mrr']:.3f}"
                )


def _check_pass_criteria(baseline: ChunkerEvaluation, candidate: ChunkerEvaluation) -> dict:
    """Apply the protocol's pass criteria and report PASS/FAIL per criterion."""
    bcat = baseline.metrics_by_category
    ccat = candidate.metrics_by_category

    heading_lift = (
        ccat.get("heading-targeted", {}).get("hit_at_1", 0.0)
        - bcat.get("heading-targeted", {}).get("hit_at_1", 0.0)
    )
    general_delta = (
        ccat.get("general", {}).get("hit_at_1", 0.0)
        - bcat.get("general", {}).get("hit_at_1", 0.0)
    )

    cs = candidate.chunk_stats

    return {
        "heading_targeted_lift_pp": round(100 * heading_lift, 2),
        "heading_targeted_lift_pass": heading_lift >= 0.05,
        "general_query_delta_pp": round(100 * general_delta, 2),
        "general_query_non_regression_pass": general_delta >= -0.02,
        "size_cap_honoured_pass": (cs is not None and cs.over_cap_count == 0),
        "size_cap_max_chars": (cs.max_length if cs else None),
        "size_cap_threshold": SIZE_CAP,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dir", type=str, required=True)
    parser.add_argument("--candidate-dir", type=str, required=True)
    args = parser.parse_args()

    baseline_dir = str(Path(args.baseline_dir).resolve())
    candidate_dir = str(Path(args.candidate_dir).resolve())

    if not Path(baseline_dir).exists():
        print(f"  ERROR: baseline ChromaDB not found: {baseline_dir}")
        print("  Run the baseline ingest first (see protocol.md Step 3)")
        sys.exit(1)
    if not Path(candidate_dir).exists():
        print(f"  ERROR: candidate ChromaDB not found: {candidate_dir}")
        sys.exit(1)

    queries = _load_ground_truth()
    print(f"Experiment 6: Markdown Chunking Quality")
    print(f"  Queries: {len(queries)}")
    print(f"  Reranker: disabled (isolate chunker effect)")

    # Reset reranker singleton just in case it was instantiated.
    try:
        from rag_mcp.reranker import CrossEncoderReranker
        CrossEncoderReranker._instance = None  # type: ignore[attr-defined]
    except Exception:
        pass

    import rag_mcp.retrieval  # noqa: F401

    print("\n  Evaluating baseline (SentenceSplitter only)...")
    baseline = _evaluate_chunker("baseline", baseline_dir, queries)

    print("  Evaluating candidate (MarkdownNodeParser → SentenceSplitter)...")
    candidate = _evaluate_chunker("candidate", candidate_dir, queries)

    _print_comparison(baseline, candidate)

    criteria = _check_pass_criteria(baseline, candidate)
    print("\n  Pass Criteria")
    print(f"  {'-' * 60}")
    for k, v in criteria.items():
        print(f"  {k}: {v}")

    output_path = EXPERIMENT_DIR / "eval_results.json"
    with open(output_path, "w") as f:
        json.dump(
            {
                "experiment": "markdown-chunking-quality",
                "baseline": asdict(baseline),
                "candidate": asdict(candidate),
                "pass_criteria": criteria,
            },
            f,
            indent=2,
        )
    print(f"\n  Raw results saved to: {output_path}")


if __name__ == "__main__":
    main()
