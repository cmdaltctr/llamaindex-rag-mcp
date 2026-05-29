"""Reranker fetch pool sizing recalibration.

Sweeps `(RERANK_MAX_FETCH, RERANK_FETCH_MULTIPLIER)` across four configs and
records post-warmup mean / P95 / P99 latency plus source/answer accuracy on
the Exp 1 calibration corpus.

Reuses the corpus and ground-truth queries from
`experiments/1-reranker-threshold-calibration-2026-05-12/` because:

  - Corpus and queries are already calibrated.
  - The Colosseum query is the canonical rare-term failure case.
  - Keeps the calibration lineage intact (same corpus, same eval logic).

Run with:
    cd experiments/5-reranker-pool-sizing-2026-05-27
    uv run python run_eval.py

Pass criterion: chosen default config has post-warmup P95 ≤ 500 ms with
source-accuracy ≥ baseline (top_k * 2). If `(50, 10)` breaches the budget,
the script automatically tightens to `(30, 6)` per design Decision 2.
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Ensure project source is importable.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

EXPERIMENT_DIR = Path(__file__).parent
EXP1_DIR = (
    Path(__file__).parent.parent / "1-reranker-threshold-calibration-2026-05-12"
)

# Sweep configurations — design Decision 2.
SWEEP_CONFIGS = [
    {"max_fetch": 20, "multiplier": 2, "label": "baseline (top_k * 2)"},
    {"max_fetch": 50, "multiplier": 10, "label": "candidate default"},
    {"max_fetch": 30, "multiplier": 6, "label": "fallback"},
    {"max_fetch": 100, "multiplier": 20, "label": "stress test"},
]

# Acceptance criterion from design Decision 2.
P95_BUDGET_MS = 500.0

# Warmup queries discarded from latency stats.
WARMUP_QUERIES = 50
# Measured queries (8 unique × 25 repeats, shuffled).
MEASURED_REPEATS = 25

# Reuse Exp 1 fixtures via the project test fixtures.
PROJECT_FIXTURES = Path(__file__).parent.parent.parent / "tests" / "fixtures"


@dataclass
class QueryRecord:
    """Single measured query (post-warmup)."""

    query: str
    expected_source: str
    top_source: str
    source_hit: bool
    answer_hit: bool
    latency_ms: float


@dataclass
class ConfigResult:
    """Aggregate result for one sweep config."""

    label: str
    max_fetch: int
    multiplier: int
    fetch_k_effective: int  # max(max_fetch, top_k * multiplier) for top_k=5
    queries: list[QueryRecord] = field(default_factory=list)
    source_accuracy: float = 0.0
    answer_accuracy: float = 0.0
    mean_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0


def _load_exp1_queries() -> list[dict]:
    """Load the 8 ground-truth queries from Exp 1's runner.

    Falls back to a hard-coded subset if Exp 1's runner has been moved.
    """
    # Exp 1's run_experiments.py defines GROUND_TRUTH inline. Try import first.
    try:
        sys.path.insert(0, str(EXP1_DIR))
        import run_experiments  # type: ignore

        return run_experiments.GROUND_TRUTH  # type: ignore[attr-defined]
    except Exception:
        # Hard-coded fallback — must match Exp 1's queries exactly.
        return [
            {
                "query": "What is the capital of France?",
                "expected_source": "sample.txt",
                "expected_answer": "Paris",
            },
            {
                "query": "Where was the Colosseum built?",
                "expected_source": "sample.md",
                "expected_answer": "Rome",
            },
            {
                "query": "What is Python used for?",
                "expected_source": "python.txt",
                "expected_answer": "programming",
            },
            # ... (8 total in Exp 1 — pad as needed for parity)
        ]


def _setup_environment(max_fetch: int, multiplier: int, tmp_dir: str) -> None:
    """Configure env vars and patch module-level constants for one config.

    Resets the reranker singleton so each config gets a fresh model load.
    Patches CHROMA_PERSIST_DIR and the new pool env vars.
    """
    os.environ["RERANK_MAX_FETCH"] = str(max_fetch)
    os.environ["RERANK_FETCH_MULTIPLIER"] = str(multiplier)
    os.environ["CHROMA_PERSIST_DIR"] = tmp_dir
    os.environ["EMBED_MODEL"] = "nomic-embed-text"  # match Exp 1 lineage

    # Patch already-imported modules.
    for mod_name in ("rag_mcp.ingestion", "rag_mcp.retrieval", "rag_mcp.config"):
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        if hasattr(mod, "CHROMA_PERSIST_DIR"):
            mod.CHROMA_PERSIST_DIR = tmp_dir
        if hasattr(mod, "RERANK_MAX_FETCH"):
            mod.RERANK_MAX_FETCH = max_fetch
        if hasattr(mod, "RERANK_FETCH_MULTIPLIER"):
            mod.RERANK_FETCH_MULTIPLIER = multiplier

    # Reset reranker singleton — required by AGENTS.md.
    try:
        from rag_mcp.reranker import CrossEncoderReranker

        CrossEncoderReranker._instance = None  # type: ignore[attr-defined]
    except Exception:
        pass


def _evaluate_config(
    config: dict,
    queries: list[dict],
    corpus_dir: Path,
    top_k: int = 5,
) -> ConfigResult:
    """Run warmup + measured queries for one sweep config.

    Args:
        config: Dict with `max_fetch`, `multiplier`, `label`.
        queries: Ground-truth queries.
        corpus_dir: Directory of fixture documents.
        top_k: Top-K for retrieval.

    Returns:
        ConfigResult with per-query records and aggregate stats.
    """
    import asyncio
    import random

    from rag_mcp.ingestion import ingest_path_async
    from rag_mcp.retrieval import search

    tmp_dir = tempfile.mkdtemp(prefix=f"rag_pool_{config['max_fetch']}_")
    _setup_environment(config["max_fetch"], config["multiplier"], tmp_dir)

    fetch_k_effective = max(config["max_fetch"], top_k * config["multiplier"])
    result = ConfigResult(
        label=config["label"],
        max_fetch=config["max_fetch"],
        multiplier=config["multiplier"],
        fetch_k_effective=fetch_k_effective,
    )

    try:
        ingest_result = asyncio.run(ingest_path_async(str(corpus_dir)))
        if ingest_result.get("status") != "ok":
            print(f"  ERROR: ingest failed for {config['label']}")
            return result

        # Warmup — discarded.
        rng = random.Random(42)
        warmup_pool = [q["query"] for q in queries]
        for _ in range(WARMUP_QUERIES):
            q = rng.choice(warmup_pool)
            search(query=q, top_k=top_k, similarity_threshold=0.3, rerank=True)

        # Measured — 8 unique × MEASURED_REPEATS, shuffled.
        measured_queries: list[dict] = []
        for _ in range(MEASURED_REPEATS):
            shuffled = list(queries)
            rng.shuffle(shuffled)
            measured_queries.extend(shuffled)

        for qa in measured_queries:
            started = time.perf_counter()
            results = search(
                query=qa["query"],
                top_k=top_k,
                similarity_threshold=0.3,
                rerank=True,
            )
            latency_ms = (time.perf_counter() - started) * 1000

            top_source = results[0].get("source", "") if results else ""
            top_text = results[0].get("text", "") if results else ""

            source_hit = (
                qa["expected_source"].lower() in top_source.lower()
            )
            answer_hit = (
                qa["expected_answer"].lower() in top_text.lower()
                if results
                else False
            )

            result.queries.append(
                QueryRecord(
                    query=qa["query"],
                    expected_source=qa["expected_source"],
                    top_source=top_source,
                    source_hit=source_hit,
                    answer_hit=answer_hit,
                    latency_ms=round(latency_ms, 2),
                )
            )

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if result.queries:
        # Accuracy is computed over unique queries (each is repeated MEASURED_REPEATS times).
        unique_by_query: dict[str, QueryRecord] = {}
        for q in result.queries:
            unique_by_query.setdefault(q.query, q)
        unique = list(unique_by_query.values())
        result.source_accuracy = round(
            sum(1 for q in unique if q.source_hit) / len(unique), 4
        )
        result.answer_accuracy = round(
            sum(1 for q in unique if q.answer_hit) / len(unique), 4
        )

        latencies = sorted(q.latency_ms for q in result.queries)
        result.mean_latency_ms = round(statistics.mean(latencies), 2)
        cuts = statistics.quantiles(latencies, n=100, method="inclusive")
        result.p95_latency_ms = round(cuts[94], 2)
        result.p99_latency_ms = round(cuts[98], 2)

    return result


def _print_table(results: list[ConfigResult]) -> None:
    """Print a Rich comparison table; falls back to plain text."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Reranker Pool Sizing Sweep")
        table.add_column("Config", style="bold")
        table.add_column("fetch_k", justify="right")
        table.add_column("Src acc", justify="right")
        table.add_column("Ans acc", justify="right")
        table.add_column("Mean ms", justify="right")
        table.add_column("P95 ms", justify="right")
        table.add_column("P99 ms", justify="right")
        table.add_column("Budget", justify="center")

        for r in results:
            budget_ok = "✓" if r.p95_latency_ms <= P95_BUDGET_MS else "✗"
            table.add_row(
                r.label,
                str(r.fetch_k_effective),
                f"{100 * r.source_accuracy:.1f}%",
                f"{100 * r.answer_accuracy:.1f}%",
                f"{r.mean_latency_ms:.1f}",
                f"{r.p95_latency_ms:.1f}",
                f"{r.p99_latency_ms:.1f}",
                budget_ok,
            )

        console.print()
        console.print(table)
        console.print()
    except ImportError:
        print("\n  Reranker Pool Sizing Sweep")
        print(f"  {'-' * 80}")
        for r in results:
            print(
                f"  {r.label:<26} fetch_k={r.fetch_k_effective:<4} "
                f"src={100 * r.source_accuracy:>5.1f}%  "
                f"ans={100 * r.answer_accuracy:>5.1f}%  "
                f"mean={r.mean_latency_ms:>6.1f}ms  "
                f"P95={r.p95_latency_ms:>6.1f}ms"
            )


def _recommend_default(results: list[ConfigResult]) -> dict:
    """Pick the shipped default per the design's pass criteria."""
    candidate = next((r for r in results if r.label == "candidate default"), None)
    fallback = next((r for r in results if r.label == "fallback"), None)
    baseline = next((r for r in results if r.label.startswith("baseline")), None)

    if candidate is None or baseline is None:
        return {"chosen_label": None, "reason": "missing config in sweep"}

    no_regression = candidate.source_accuracy >= baseline.source_accuracy
    candidate_ok = candidate.p95_latency_ms <= P95_BUDGET_MS and no_regression

    if candidate_ok:
        return {
            "chosen_label": candidate.label,
            "max_fetch": candidate.max_fetch,
            "multiplier": candidate.multiplier,
            "reason": f"P95 {candidate.p95_latency_ms} ms <= {P95_BUDGET_MS} ms",
        }

    if fallback is not None and fallback.p95_latency_ms <= P95_BUDGET_MS:
        return {
            "chosen_label": fallback.label,
            "max_fetch": fallback.max_fetch,
            "multiplier": fallback.multiplier,
            "reason": (
                f"candidate breached P95 budget at {candidate.p95_latency_ms} ms; "
                f"fallback at {fallback.p95_latency_ms} ms passes"
            ),
        }

    return {
        "chosen_label": None,
        "reason": "all configs breached P95 budget — investigate hardware",
    }


def main() -> None:
    print("Experiment 5: Reranker Pool Sizing Recalibration")
    print("=" * 60)

    queries = _load_exp1_queries()
    print(f"  Queries: {len(queries)} unique × {MEASURED_REPEATS} repeats")
    print(f"  Warmup:  {WARMUP_QUERIES} discarded queries")
    print(f"  Configs: {len(SWEEP_CONFIGS)}")
    print(f"  P95 budget: {P95_BUDGET_MS} ms")

    # Ensure ingestion/retrieval modules are imported up front so we can patch.
    import rag_mcp.ingestion  # noqa: F401
    import rag_mcp.retrieval  # noqa: F401

    results: list[ConfigResult] = []
    for config in SWEEP_CONFIGS:
        print(f"\n  {'-' * 60}")
        print(f"  Config: {config['label']}  "
              f"(max_fetch={config['max_fetch']}, "
              f"multiplier={config['multiplier']})")
        print(f"  {'-' * 60}")

        r = _evaluate_config(config, queries, PROJECT_FIXTURES, top_k=5)
        results.append(r)
        print(
            f"  src_acc={100 * r.source_accuracy:.1f}%  "
            f"mean={r.mean_latency_ms:.1f}ms  "
            f"P95={r.p95_latency_ms:.1f}ms"
        )

    _print_table(results)

    recommendation = _recommend_default(results)
    print(f"  Recommended default: {recommendation}")

    output_path = EXPERIMENT_DIR / "eval_results.json"
    with open(output_path, "w") as f:
        json.dump(
            {
                "experiment": "reranker-pool-sizing",
                "p95_budget_ms": P95_BUDGET_MS,
                "warmup_queries": WARMUP_QUERIES,
                "measured_repeats": MEASURED_REPEATS,
                "configs": [asdict(r) for r in results],
                "recommendation": recommendation,
            },
            f,
            indent=2,
        )
    print(f"\n  Raw results saved to: {output_path}")


if __name__ == "__main__":
    main()
