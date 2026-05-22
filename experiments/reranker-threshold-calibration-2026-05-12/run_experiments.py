"""RAG retrieval quality experiments.

Measures search quality with and without the cross-encoder reranker,
and with different similarity thresholds. Uses the test fixture documents
as ground truth.

Run with:
    uv run python docs/run_experiments.py

Requires Ollama running with nomic-embed-text pulled.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Ensure project source is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

# ── Ground-truth QA pairs ──────────────────────────────────────────────────
# Each pair has a query and the expected source file that should appear
# in the top results. These are based on the test fixture content.

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"

QA_PAIRS: list[dict] = [
    {
        "query": "What is the capital of France?",
        "expected_source_substring": "sample",
        "expected_answer_substring": "Paris",
        "category": "geography",
    },
    {
        "query": "Which city has the Eiffel Tower?",
        "expected_source_substring": "sample",
        "expected_answer_substring": "Paris",
        "category": "geography",
    },
    {
        "query": "Tell me about Python programming",
        "expected_source_substring": "python",
        "expected_answer_substring": "data science",
        "category": "programming",
    },
    {
        "query": "What is JavaScript used for?",
        "expected_source_substring": "javascript",
        "expected_answer_substring": "web development",
        "category": "programming",
    },
    {
        "query": "What is the capital of Germany?",
        "expected_source_substring": "sample",
        "expected_answer_substring": "Berlin",
        "category": "geography",
    },
    {
        "query": "What is the Colosseum?",
        "expected_source_substring": "sample",
        "expected_answer_substring": "Rome",
        "category": "geography",
    },
    {
        "query": "Tell me about machine learning libraries",
        "expected_source_substring": "python",
        "expected_answer_substring": "scikit-learn",
        "category": "programming",
    },
    {
        "query": "What runs on the server with Node.js?",
        "expected_source_substring": "javascript",
        "expected_answer_substring": "JavaScript",
        "category": "programming",
    },
]


@dataclass
class QueryResult:
    """Single query result for reporting."""

    query: str
    category: str
    rerank: bool
    similarity_threshold: float
    top_k: int
    num_results: int
    top_source: str
    top_score: float
    source_correct: bool
    answer_correct: bool
    latency_ms: float
    all_scores: list[float] = field(default_factory=list)


def run_experiment(
    rerank: bool = False,
    similarity_threshold: float = 0.0,
    top_k: int = 5,
) -> list[QueryResult]:
    """Run all QA pairs through the retrieval pipeline with given params."""
    from rag_mcp.ingestion import ingest_path
    from rag_mcp.retrieval import search

    # Ingest fixtures
    print(f"  Ingesting fixtures from {FIXTURES_DIR}...")
    ingest_result = ingest_path(str(FIXTURES_DIR))
    print(
        f"  Indexed {ingest_result.get('files_indexed', 0)} files, "
        f"{ingest_result.get('chunks_created', 0)} chunks"
    )

    results: list[QueryResult] = []

    for qa in QA_PAIRS:
        start = time.perf_counter()
        search_results = search(
            query=qa["query"],
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            rerank=rerank,
        )
        latency_ms = (time.perf_counter() - start) * 1000

        # Evaluate source correctness
        source_correct = False
        answer_correct = False
        top_source = ""
        top_score = 0.0

        if search_results:
            top_source = search_results[0].get("source", "")
            top_score = search_results[0].get("score", 0.0)
            top_text = search_results[0].get("text", "")

            source_correct = (
                qa["expected_source_substring"].lower() in top_source.lower()
            )
            answer_correct = (
                qa["expected_answer_substring"].lower() in top_text.lower()
            )

        results.append(
            QueryResult(
                query=qa["query"],
                category=qa["category"],
                rerank=rerank,
                similarity_threshold=similarity_threshold,
                top_k=top_k,
                num_results=len(search_results),
                top_source=top_source,
                top_score=top_score,
                source_correct=source_correct,
                answer_correct=answer_correct,
                latency_ms=round(latency_ms, 1),
                all_scores=[r.get("score", 0.0) for r in search_results],
            )
        )

    return results


def print_report(
    label: str,
    results: list[QueryResult],
) -> dict:
    """Print a summary report and return aggregate metrics."""
    total = len(results)
    source_hits = sum(1 for r in results if r.source_correct)
    answer_hits = sum(1 for r in results if r.answer_correct)
    avg_latency = sum(r.latency_ms for r in results) / total if total else 0
    avg_score = (
        sum(r.top_score for r in results) / total if total else 0
    )

    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(f"  Queries:            {total}")
    print(f"  Source accuracy:    {source_hits}/{total} "
          f"({100 * source_hits / total:.1f}%)")
    print(f"  Answer accuracy:    {answer_hits}/{total} "
          f"({100 * answer_hits / total:.1f}%)")
    print(f"  Avg top-1 score:    {avg_score:.4f}")
    print(f"  Avg latency:        {avg_latency:.1f} ms")
    print()

    # Per-query detail
    print(f"  {'Query':<42} {'Src':>4} {'Ans':>4} {'Score':>7} {'ms':>8}")
    print(f"  {'-' * 42} {'-' * 4} {'-' * 4} {'-' * 7} {'-' * 8}")
    for r in results:
        src_mark = "✓" if r.source_correct else "✗"
        ans_mark = "✓" if r.answer_correct else "✗"
        query_short = r.query[:40] + ".." if len(r.query) > 42 else r.query
        print(
            f"  {query_short:<42} {src_mark:>4} {ans_mark:>4} "
            f"{r.top_score:>7.4f} {r.latency_ms:>7.1f}ms"
        )

    return {
        "label": label,
        "total_queries": total,
        "source_accuracy": round(source_hits / total, 3) if total else 0,
        "answer_accuracy": round(answer_hits / total, 3) if total else 0,
        "avg_score": round(avg_score, 4),
        "avg_latency_ms": round(avg_latency, 1),
    }


def main() -> None:
    """Run all experiment configurations and output results."""
    print("RAG Retrieval Quality Experiments")
    print("=" * 60)
    print()

    # Check if Ollama is running
    import urllib.request
    import urllib.error

    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=3)
        print(f"  Ollama is running at {ollama_url}")
    except urllib.error.URLError:
        print(
            f"  ERROR: Ollama is not reachable at {ollama_url}\n"
            "  Start it with: ollama serve\n"
            "  Then pull the model: ollama pull nomic-embed-text"
        )
        sys.exit(1)

    # Use a temporary ChromaDB to avoid polluting the real one
    import tempfile

    tmp_dir = tempfile.mkdtemp(prefix="rag_experiment_")
    os.environ["CHROMA_PERSIST_DIR"] = tmp_dir
    os.environ["COLLECTION_NAME"] = "experiment_documents"

    # Patch module-level constants for modules already loaded
    import sys as _sys

    for mod_name in ("rag_mcp.ingestion", "rag_mcp.retrieval"):
        mod = _sys.modules.get(mod_name)
        if mod is not None:
            mod.CHROMA_PERSIST_DIR = tmp_dir
            mod.COLLECTION_NAME = "experiment_documents"

    print(f"  Using temp ChromaDB: {tmp_dir}")
    print()

    all_summaries: list[dict] = []

    # ── Experiment 1: Vector search only (no reranker) ────────────────
    print("\n▶ Experiment 1: Vector search only")
    results_v = run_experiment(rerank=False, similarity_threshold=0.0)
    summary_v = print_report("Vector Search (no reranker)", results_v)
    all_summaries.append(summary_v)

    # ── Experiment 2: Vector search + reranker ────────────────────────
    print("\n▶ Experiment 2: Vector search + cross-encoder reranker")
    results_r = run_experiment(rerank=True, similarity_threshold=0.0)
    summary_r = print_report("Vector Search + Reranker", results_r)
    all_summaries.append(summary_r)

    # ── Experiment 3: Vector search + similarity threshold ────────────
    print("\n▶ Experiment 3: Vector search with threshold=0.3")
    results_t = run_experiment(rerank=False, similarity_threshold=0.3)
    summary_t = print_report("Vector + threshold=0.3", results_t)
    all_summaries.append(summary_t)

    # ── Experiment 4: Full pipeline (reranker + threshold) ────────────
    print("\n▶ Experiment 4: Full pipeline (reranker + threshold=0.3)")
    results_f = run_experiment(rerank=True, similarity_threshold=0.3)
    summary_f = print_report("Full Pipeline (rerank + threshold)", results_f)
    all_summaries.append(summary_f)

    # ── Comparison table ──────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  COMPARISON SUMMARY")
    print(f"{'=' * 60}")
    print()
    header = (
        f"  {'Configuration':<35} {'Src%':>6} {'Ans%':>6} "
        f"{'Score':>7} {'Latency':>9}"
    )
    print(header)
    print(f"  {'-' * 35} {'-' * 6} {'-' * 6} {'-' * 7} {'-' * 9}")
    for s in all_summaries:
        print(
            f"  {s['label']:<35} "
            f"{100 * s['source_accuracy']:>5.1f}% "
            f"{100 * s['answer_accuracy']:>5.1f}% "
            f"{s['avg_score']:>7.4f} "
            f"{s['avg_latency_ms']:>7.1f}ms"
        )
    print()

    # Save raw results to JSON
    output_path = Path(__file__).parent / "experiment_results.json"
    with open(output_path, "w") as f:
        json.dump(
            {
                "summaries": all_summaries,
                "detailed_results": {
                    "vector_only": [asdict(r) for r in results_v],
                    "vector_plus_reranker": [asdict(r) for r in results_r],
                    "vector_plus_threshold": [asdict(r) for r in results_t],
                    "full_pipeline": [asdict(r) for r in results_f],
                },
            },
            f,
            indent=2,
        )
    print(f"  Detailed results saved to: {output_path}")

    # Clean up temp directory
    import shutil

    shutil.rmtree(tmp_dir, ignore_errors=True)
    print(f"  Cleaned up temp ChromaDB")


if __name__ == "__main__":
    main()
