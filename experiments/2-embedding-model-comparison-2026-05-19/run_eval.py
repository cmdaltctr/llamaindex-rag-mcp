"""Embedding model retrieval quality comparison.

Compares retrieval quality between two embedding models by measuring
Hit Rate@K and MRR on a user-defined set of ground-truth queries.
Each model gets its own temporary ChromaDB to avoid dimension conflicts.

Run with:
    cd experiments/embedding-model-comparison-2026-05-19
    uv run python run_eval.py

Requires Ollama running with both models pulled:
    ollama pull nomic-embed-text
    ollama pull qwen3-embedding:0.6b
"""

# NOTE (v2.0.0): this script targets the PRE-v2.0.0 import surface
# (omrg.ingestion, omrg.retrieval, omrg.reranker, ...), which was
# removed by the architecture-v2 conformance change. It is an archived
# historical artefact, is not run in CI, and is intentionally NOT repaired:
# its results are already recorded in results.md, and rewriting it would
# change the code that produced them. See docs/adr/037.


from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Ensure project source is importable.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
EXPERIMENT_DIR = Path(__file__).parent
CORPUS_DIR = EXPERIMENT_DIR / "corpus"
GROUND_TRUTH_PATH = EXPERIMENT_DIR / "ground-truth.json"
FIXTURES_DIR = Path(__file__).parent.parent.parent / "tests" / "fixtures"

# ── Models to compare ──────────────────────────────────────────────────────
MODELS = [
    {"name": "nomic-embed-text", "label": "nomic-embed-text (768-dim)"},
    {"name": "qwen3-embedding:0.6b", "label": "qwen3-embedding:0.6b (1024-dim)"},
    {"name": "qwen3-embedding:8b", "label": "qwen3-embedding:8b (4096-dim)"},
]

# ── Collection name for experiment (must be unique per run) ────────────────
EXPERIMENT_COLLECTION = "eval_quality_documents"


# ── Data classes ───────────────────────────────────────────────────────────


@dataclass
class QueryResult:
    """Result of a single query against a single model."""

    query: str
    expected_source: str
    expected_answer: str | None
    top_k_sources: list[str] = field(default_factory=list)
    top_k_scores: list[float] = field(default_factory=list)
    hit_rank: int | None = None  # 1-indexed position of first correct doc
    hit_at_1: bool = False
    hit_at_3: bool = False
    hit_at_5: bool = False
    latency_ms: float = 0.0


@dataclass
class ModelEvaluation:
    """Aggregate evaluation results for a single model."""

    model_name: str
    label: str
    queries: list[QueryResult] = field(default_factory=list)
    hit_rate_at_1: float = 0.0
    hit_rate_at_3: float = 0.0
    hit_rate_at_5: float = 0.0
    mrr: float = 0.0
    avg_latency_ms: float = 0.0


# ── Helpers ────────────────────────────────────────────────────────────────


def _check_ollama() -> None:
    """Verify that Ollama is reachable and both models are available."""
    import urllib.error
    import urllib.request

    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        resp = urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=5)
        data = json.loads(resp.read())
    except urllib.error.URLError:
        print(
            f"  ERROR: Ollama is not reachable at {ollama_url}\n"
            "  Start it with: ollama serve\n"
            "  Then pull both models:\n"
            "    ollama pull nomic-embed-text\n"
            "    ollama pull qwen3-embedding:0.6b"
        )
        sys.exit(1)

    available = {
        m.get("name", "").split(":")[0] for m in data.get("models", [])
    }
    for model_info in MODELS:
        model_base = model_info["name"].split(":")[0]
        if model_base not in available:
            print(
                f"  ERROR: Model '{model_info['name']}' is not pulled.\n"
                f"  Run: ollama pull {model_info['name']}"
            )
            sys.exit(1)


def _load_ground_truth() -> list[dict]:
    """Load and validate the ground-truth query set.

    Returns:
        List of query objects with 'query', 'expected_source', and
        optionally 'expected_answer' keys.

    Raises:
        SystemExit: If the ground-truth file is missing or malformed.
    """
    if not GROUND_TRUTH_PATH.exists():
        print(
            f"  ERROR: Ground-truth file not found: {GROUND_TRUTH_PATH}\n"
            "  Copy the template and fill in your queries."
        )
        sys.exit(1)

    with open(GROUND_TRUTH_PATH) as f:
        data = json.load(f)

    queries = data.get("queries", [])
    if not queries:
        print("  ERROR: No queries found in ground-truth.json.")
        sys.exit(1)

    # Validate required fields.
    for i, q in enumerate(queries):
        if "query" not in q or "expected_source" not in q:
            print(
                f"  ERROR: Query at index {i} is missing 'query' or "
                f"'expected_source'. Got keys: {list(q.keys())}"
            )
            sys.exit(1)

    return queries


def _resolve_corpus() -> Path:
    """Determine the corpus directory to use.

    Returns:
        Path to the corpus directory.

    Raises:
        SystemExit: If no corpus files are found anywhere.
    """
    # Check if user has placed real documents in corpus/.
    supported = {".pdf", ".docx", ".pptx", ".txt", ".md", ".html", ".csv"}
    if CORPUS_DIR.exists():
        corpus_files = [
            f for f in CORPUS_DIR.rglob("*") if f.suffix.lower() in supported
        ]
        if corpus_files:
            print(f"  Using corpus: {CORPUS_DIR} ({len(corpus_files)} files)")
            return CORPUS_DIR

    # Fall back to test fixtures so the user can verify the script works.
    if FIXTURES_DIR.exists():
        fixture_files = [
            f
            for f in FIXTURES_DIR.rglob("*")
            if f.suffix.lower() in supported and f.name != "empty.txt"
        ]
        if fixture_files:
            print(
                f"  WARNING: corpus/ is empty — using test fixtures instead.\n"
                f"  Fixtures: {FIXTURES_DIR} ({len(fixture_files)} files)\n"
                f"  Place your own documents in {CORPUS_DIR}/ for real results."
            )
            return FIXTURES_DIR

    print(
        "  ERROR: No documents found.\n"
        f"  Place PDF/MD/TXT files in: {CORPUS_DIR}/\n"
        "  Or ensure test fixtures exist at tests/fixtures/."
    )
    sys.exit(1)


def _setup_model(model_name: str, tmp_dir: str) -> None:
    """Configure the embedding model and ChromaDB for evaluation.

    Creates a fresh OllamaEmbedding for the given model name and patches
    the module-level constants so that ingestion and retrieval use the
    temporary ChromaDB.

    Args:
        model_name: Ollama model name (e.g. 'nomic-embed-text').
        tmp_dir: Path to the temporary ChromaDB directory.
    """
    from llama_index.core import Settings
    from llama_index.embeddings.ollama import OllamaEmbedding

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # Create a fresh embedding model instance.
    Settings.embed_model = OllamaEmbedding(
        model_name=model_name,
        base_url=base_url,
        embed_batch_size=int(os.getenv("EMBED_BATCH_SIZE", "100")),
    )

    # Patch module-level constants for modules that have already been
    # imported (or will be imported).  This is the same pattern used in
    # experiment-1.
    os.environ["CHROMA_PERSIST_DIR"] = tmp_dir
    os.environ["COLLECTION_NAME"] = EXPERIMENT_COLLECTION

    for mod_name in ("omrg.ingestion", "omrg.retrieval", "omrg.config"):
        mod = sys.modules.get(mod_name)
        if mod is not None:
            if hasattr(mod, "CHROMA_PERSIST_DIR"):
                mod.CHROMA_PERSIST_DIR = tmp_dir
            if hasattr(mod, "COLLECTION_NAME"):
                mod.COLLECTION_NAME = EXPERIMENT_COLLECTION


def _clear_chroma(tmp_dir: str) -> None:
    """Delete and recreate the ChromaDB directory for a clean run.

    Args:
        tmp_dir: Path to the ChromaDB directory.
    """
    shutil.rmtree(tmp_dir, ignore_errors=True)
    os.makedirs(tmp_dir, exist_ok=True)


# ── Core evaluation ───────────────────────────────────────────────────────


def evaluate_model(
    model_info: dict,
    ground_truth: list[dict],
    corpus_dir: Path,
) -> ModelEvaluation:
    """Run all queries against a single embedding model.

    Sets up a fresh ChromaDB, ingests the corpus, and evaluates each query.
    Reranking is disabled so we isolate embedding model quality.

    Args:
        model_info: Dict with 'name' and 'label' keys.
        ground_truth: List of ground-truth query objects.
        corpus_dir: Path to the directory of documents to ingest.

    Returns:
        ModelEvaluation with per-query and aggregate results.
    """
    from omrg.ingestion import ingest_path
    from omrg.retrieval import search

    model_name = model_info["name"]
    label = model_info["label"]
    eval_result = ModelEvaluation(model_name=model_name, label=label)

    # Create a temporary ChromaDB for this model (each model produces
    # different-dimension vectors that cannot coexist in one collection).
    tmp_dir = tempfile.mkdtemp(prefix=f"rag_eval_{model_name.replace(':', '_')}_")
    _setup_model(model_name, tmp_dir)

    try:
        # Ingest the corpus.
        print(f"\n  Ingesting corpus with {model_name}...")
        ingest_result = ingest_path(str(corpus_dir))
        if ingest_result.get("status") != "ok":
            print(
                f"  ERROR: Ingestion failed for {model_name}: "
                f"{ingest_result.get('message', 'unknown error')}"
            )
            return eval_result

        print(
            f"  Indexed {ingest_result.get('files_indexed', 0)} files, "
            f"{ingest_result.get('chunks_created', 0)} chunks"
        )

        # Run queries.
        for qa in ground_truth:
            query_text = qa["query"]
            expected_source = qa["expected_source"]
            expected_answer = qa.get("expected_answer")

            start = time.perf_counter()
            results = search(
                query=query_text,
                top_k=5,
                similarity_threshold=0.0,
                rerank=False,  # Isolate embedding model quality.
            )
            latency_ms = (time.perf_counter() - start) * 1000

            # Extract sources and scores from top results.
            top_sources = [
                r.get("source", "") for r in results[:5]
            ]
            top_scores = [
                r.get("score", 0.0) for r in results[:5]
            ]

            # Find the rank of the first result whose source contains
            # the expected_source substring (case-insensitive).
            hit_rank = None
            for rank, source in enumerate(top_sources, start=1):
                if expected_source.lower() in source.lower():
                    hit_rank = rank
                    break

            qr = QueryResult(
                query=query_text,
                expected_source=expected_source,
                expected_answer=expected_answer,
                top_k_sources=top_sources,
                top_k_scores=top_scores,
                hit_rank=hit_rank,
                hit_at_1=(hit_rank is not None and hit_rank <= 1),
                hit_at_3=(hit_rank is not None and hit_rank <= 3),
                hit_at_5=(hit_rank is not None and hit_rank <= 5),
                latency_ms=round(latency_ms, 1),
            )
            eval_result.queries.append(qr)

    finally:
        # Clean up temp ChromaDB.
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Compute aggregate metrics.
    n = len(eval_result.queries)
    if n > 0:
        eval_result.hit_rate_at_1 = sum(
            1 for q in eval_result.queries if q.hit_at_1
        ) / n
        eval_result.hit_rate_at_3 = sum(
            1 for q in eval_result.queries if q.hit_at_3
        ) / n
        eval_result.hit_rate_at_5 = sum(
            1 for q in eval_result.queries if q.hit_at_5
        ) / n
        # MRR: mean of 1/rank for queries that hit, 0 for misses.
        reciprocal_ranks = [
            (1.0 / q.hit_rank if q.hit_rank else 0.0)
            for q in eval_result.queries
        ]
        eval_result.mrr = sum(reciprocal_ranks) / n
        eval_result.avg_latency_ms = round(
            sum(q.latency_ms for q in eval_result.queries) / n, 1
        )

    return eval_result


# ── Reporting ──────────────────────────────────────────────────────────────


def _print_per_query_detail(label: str, evaluation: ModelEvaluation) -> None:
    """Print per-query results for a single model.

    Args:
        label: Section header label.
        evaluation: The model evaluation results.
    """
    print(f"\n  {label}")
    print(f"  {'─' * 80}")
    print(
        f"  {'Query':<50} {'Rank':>5} {'Hit@1':>6} "
        f"{'Hit@3':>6} {'Score':>8} {'ms':>7}"
    )
    print(
        f"  {'-' * 50} {'-' * 5} {'-' * 6} "
        f"{'-' * 6} {'-' * 8} {'-' * 7}"
    )
    for q in evaluation.queries:
        rank_str = str(q.hit_rank) if q.hit_rank else "—"
        h1 = "✓" if q.hit_at_1 else "✗"
        h3 = "✓" if q.hit_at_3 else "✗"
        top_score = q.top_k_scores[0] if q.top_k_scores else 0.0
        query_short = (
            q.query[:48] + ".." if len(q.query) > 50 else q.query
        )
        print(
            f"  {query_short:<50} {rank_str:>5} {h1:>6} "
            f"{h3:>6} {top_score:>8.4f} {q.latency_ms:>6.1f}ms"
        )


def _print_comparison_table(evaluations: list[ModelEvaluation]) -> None:
    """Print a side-by-side comparison table using Rich.

    Falls back to plain text if Rich is not available.

    Args:
        evaluations: List of model evaluation results.
    """
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Embedding Model Comparison")
        table.add_column("Model", style="bold", no_wrap=True)
        table.add_column("Hit@1", justify="right")
        table.add_column("Hit@3", justify="right")
        table.add_column("Hit@5", justify="right")
        table.add_column("MRR", justify="right")
        table.add_column("Avg Latency", justify="right")

        for ev in evaluations:
            table.add_row(
                ev.model_name,
                f"{100 * ev.hit_rate_at_1:.1f}%",
                f"{100 * ev.hit_rate_at_3:.1f}%",
                f"{100 * ev.hit_rate_at_5:.1f}%",
                f"{ev.mrr:.3f}",
                f"{ev.avg_latency_ms:.1f} ms",
            )

        console.print()
        console.print(table)
        console.print()

    except ImportError:
        # Fallback: plain text table.
        print()
        print("  Embedding Model Comparison")
        print(f"  {'─' * 72}")
        print(
            f"  {'Model':<30} {'Hit@1':>8} {'Hit@3':>8} "
            f"{'Hit@5':>8} {'MRR':>6} {'Latency':>10}"
        )
        print(
            f"  {'-' * 30} {'-' * 8} {'-' * 8} "
            f"{'-' * 8} {'-' * 6} {'-' * 10}"
        )
        for ev in evaluations:
            print(
                f"  {ev.model_name:<30} "
                f"{100 * ev.hit_rate_at_1:>7.1f}% "
                f"{100 * ev.hit_rate_at_3:>7.1f}% "
                f"{100 * ev.hit_rate_at_5:>7.1f}% "
                f"{ev.mrr:>6.3f} "
                f"{ev.avg_latency_ms:>8.1f} ms"
            )
        print()


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> None:
    """Run the embedding model retrieval quality comparison."""
    print("Experiment 2: Embedding Model Retrieval Quality Comparison")
    print("=" * 60)

    # Pre-flight checks.
    _check_ollama()
    ground_truth = _load_ground_truth()
    corpus_dir = _resolve_corpus()

    print(f"  Queries: {len(ground_truth)}")
    print(f"  Models: {', '.join(m['name'] for m in MODELS)}")
    print(f"  Reranking: disabled (isolating embedding quality)")

    # Ensure ingestion/retrieval modules are loaded so we can patch them.
    import omrg.ingestion  # noqa: F401
    import omrg.retrieval  # noqa: F401

    evaluations: list[ModelEvaluation] = []

    for model_info in MODELS:
        print(f"\n{'─' * 60}")
        print(f"  Evaluating: {model_info['label']}")
        print(f"{'─' * 60}")

        ev = evaluate_model(model_info, ground_truth, corpus_dir)
        evaluations.append(ev)

        _print_per_query_detail(model_info["label"], ev)
        print(
            f"\n  Summary: Hit@1={100 * ev.hit_rate_at_1:.1f}%  "
            f"Hit@3={100 * ev.hit_rate_at_3:.1f}%  "
            f"Hit@5={100 * ev.hit_rate_at_5:.1f}%  "
            f"MRR={ev.mrr:.3f}  "
            f"Latency={ev.avg_latency_ms:.1f}ms"
        )

    # Comparison table.
    print(f"\n{'=' * 60}")
    _print_comparison_table(evaluations)

    # Save raw results.
    output_path = EXPERIMENT_DIR / "eval_results.json"
    with open(output_path, "w") as f:
        json.dump(
            {
                "experiment": "embedding-model-retrieval-quality",
                "models_tested": [
                    {"name": m["name"], "label": m["label"]} for m in MODELS
                ],
                "reranking_enabled": False,
                "num_queries": len(ground_truth),
                "corpus_dir": str(corpus_dir),
                "summaries": [
                    {
                        "model_name": ev.model_name,
                        "label": ev.label,
                        "hit_rate_at_1": round(ev.hit_rate_at_1, 4),
                        "hit_rate_at_3": round(ev.hit_rate_at_3, 4),
                        "hit_rate_at_5": round(ev.hit_rate_at_5, 4),
                        "mrr": round(ev.mrr, 4),
                        "avg_latency_ms": ev.avg_latency_ms,
                    }
                    for ev in evaluations
                ],
                "detailed_results": {
                    ev.model_name: [asdict(q) for q in ev.queries]
                    for ev in evaluations
                },
            },
            f,
            indent=2,
        )
    print(f"  Results saved to: {output_path}")

    # Print recommendation.
    if len(evaluations) >= 2:
        print(f"\n  {'─' * 60}")
        print("  Speed leader:  ", min(evaluations, key=lambda e: e.avg_latency_ms).model_name,
              f"({min(e.mrr for e in evaluations):.1%} MRR)")
        print("  Quality leader:", max(evaluations, key=lambda e: e.mrr).model_name,
              f"({max(e.mrr for e in evaluations):.3f} MRR)")
        print(f"  {'─' * 60}")

        # Pairwise comparison of highest-MRR vs fastest model.
        quality_best = max(evaluations, key=lambda e: e.mrr)
        speed_best = min(evaluations, key=lambda e: e.avg_latency_ms)
        if quality_best.model_name != speed_best.model_name:
            delta = quality_best.mrr - speed_best.mrr
            speed_ratio = (
                quality_best.avg_latency_ms / speed_best.avg_latency_ms
                if speed_best.avg_latency_ms > 0
                else float("inf")
            )
            print(
                f"\n  Recommendation: {quality_best.model_name} has highest MRR "
                f"({quality_best.mrr:.3f}), while {speed_best.model_name} "
                f"is {speed_ratio:.1f}× faster ({speed_best.avg_latency_ms:.1f}ms vs "
                f"{quality_best.avg_latency_ms:.1f}ms)."
            )
            if delta < 0.05:
                print(
                    "  The MRR gap (< 0.05) is small. Consider the faster model "
                    "unless retrieval precision is critical."
                )
            else:
                print(
                    "  The MRR gap (>= 0.05) is meaningful. The quality gain may "
                    "justify the throughput trade-off."
                )
        else:
            print(
                f"\n  {quality_best.model_name} is both the fastest and most "
                f"accurate model — unambiguous choice."
            )
    print()


if __name__ == "__main__":
    main()
