"""Async chunking responsiveness under ingest load.

Spawns an ingest coroutine and a query coroutine concurrently, records
per-query latency, and reports P50/P95/P99 latency for each run mode.

Two modes:
    idle-baseline   Fire queries against a quiescent server (no ingest running).
    under-load      Fire queries while a large file is being ingested.

Run with:
    cd experiments/4-async-chunking-responsiveness-2026-05-27

    # Step 1: ingest a small fixture so search has something to retrieve.
    CHROMA_PERSIST_DIR=./chroma_db_test \\
        uv run rag-mcp ingest tests/fixtures/sample.txt

    # Step 2: idle baseline (run 3 times, take the median).
    CHROMA_PERSIST_DIR=./chroma_db_test \\
        uv run python run_eval.py --mode idle-baseline \\
        --queries 100 --cadence-ms 100 --output idle-baseline.json

    # Step 3: under-load run.
    CHROMA_PERSIST_DIR=./chroma_db_test \\
        uv run python run_eval.py --mode under-load \\
        --ingest-path ./corpus --queries 100 --cadence-ms 100 \\
        --output under-load-postfix.json

Compare under-load.P95 to idle-baseline.P95. Pass criterion: ratio <= 2.0.
"""

# NOTE (v2.0.0): this script targets the PRE-v2.0.0 import surface
# (omrg.ingestion, omrg.retrieval, omrg.reranker, ...), which was
# removed by the architecture-v2 conformance change. It is an archived
# historical artefact, is not run in CI, and is intentionally NOT repaired:
# its results are already recorded in results.md, and rewriting it would
# change the code that produced them. See docs/adr/037.


from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Ensure project source is importable.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

EXPERIMENT_DIR = Path(__file__).parent
CORPUS_DIR = EXPERIMENT_DIR / "corpus"

# A small set of throwaway queries — we only care about latency, not accuracy.
DEFAULT_QUERIES = [
    "What does the document discuss?",
    "Summarise the main argument",
    "What are the key conclusions?",
    "Which methodology is used?",
    "What is the dependent variable?",
]


@dataclass
class QueryTiming:
    """Single query timing record."""

    index: int
    started_at_ms: float  # since run start
    latency_ms: float
    error: str | None = None


@dataclass
class RunResult:
    """Aggregate result for one mode."""

    mode: str
    queries: list[QueryTiming] = field(default_factory=list)
    ingest_wall_clock_s: float | None = None
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    error_count: int = 0


async def _query_loop(
    queries_to_fire: int,
    cadence_ms: int,
    queries_pool: list[str],
    run_start: float,
) -> list[QueryTiming]:
    """Fire `queries_to_fire` queries spaced by `cadence_ms`.

    Args:
        queries_to_fire: Total queries to send.
        cadence_ms: Milliseconds between query starts.
        queries_pool: Round-robin pool of query strings.
        run_start: `time.perf_counter()` value at run start.

    Returns:
        List of QueryTiming records.
    """
    from omrg.retrieval import search

    timings: list[QueryTiming] = []
    cadence_s = cadence_ms / 1000.0

    for i in range(queries_to_fire):
        target_start = run_start + i * cadence_s
        delay = target_start - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)

        q = queries_pool[i % len(queries_pool)]
        started = time.perf_counter()
        error: str | None = None

        try:
            # `search` is currently sync; offload so we don't hold the loop.
            await asyncio.to_thread(
                search,
                query=q,
                top_k=5,
                similarity_threshold=0.0,
                rerank=False,
            )
        except Exception as exc:  # noqa: BLE001
            error = repr(exc)

        latency_ms = (time.perf_counter() - started) * 1000
        timings.append(
            QueryTiming(
                index=i,
                started_at_ms=(started - run_start) * 1000,
                latency_ms=round(latency_ms, 2),
                error=error,
            )
        )

    return timings


async def _ingest_task(corpus_path: Path) -> float:
    """Run `ingest_path_async` on the corpus and return wall-clock seconds.

    Args:
        corpus_path: Directory or single file to ingest.

    Returns:
        Ingest wall-clock seconds.
    """
    from omrg.ingestion import ingest_path_async

    started = time.perf_counter()
    await ingest_path_async(str(corpus_path))
    return time.perf_counter() - started


async def _run_idle_baseline(args: argparse.Namespace) -> RunResult:
    """Fire queries against a quiescent server."""
    print(f"  Mode: idle-baseline ({args.queries} queries @ {args.cadence_ms} ms)")
    run_start = time.perf_counter()
    timings = await _query_loop(
        queries_to_fire=args.queries,
        cadence_ms=args.cadence_ms,
        queries_pool=DEFAULT_QUERIES,
        run_start=run_start,
    )
    return _summarise("idle-baseline", timings, ingest_wall_clock_s=None)


async def _run_under_load(args: argparse.Namespace) -> RunResult:
    """Fire queries while ingestion runs concurrently."""
    if args.ingest_path is None:
        print("  ERROR: --ingest-path is required for under-load mode")
        sys.exit(1)
    corpus = Path(args.ingest_path).resolve()
    if not corpus.exists():
        print(f"  ERROR: ingest path not found: {corpus}")
        sys.exit(1)

    print(f"  Mode: under-load ({args.queries} queries @ {args.cadence_ms} ms)")
    print(f"  Ingest target: {corpus}")

    run_start = time.perf_counter()
    ingest = asyncio.create_task(_ingest_task(corpus))
    # Give ingest a small head start so chunking is in flight when queries start.
    await asyncio.sleep(0.2)
    queries = asyncio.create_task(
        _query_loop(args.queries, args.cadence_ms, DEFAULT_QUERIES, run_start)
    )

    timings, ingest_seconds = await asyncio.gather(queries, ingest)
    return _summarise("under-load", timings, ingest_wall_clock_s=ingest_seconds)


def _summarise(
    mode: str,
    timings: list[QueryTiming],
    ingest_wall_clock_s: float | None,
) -> RunResult:
    """Compute P50/P95/P99 and pack into a RunResult."""
    latencies = [t.latency_ms for t in timings if t.error is None]
    error_count = sum(1 for t in timings if t.error is not None)

    if latencies:
        sorted_lat = sorted(latencies)
        p50 = statistics.median(sorted_lat)
        # statistics.quantiles uses 100-quantiles for percentile-style cuts.
        cuts = statistics.quantiles(sorted_lat, n=100, method="inclusive")
        p95 = cuts[94]
        p99 = cuts[98]
    else:
        p50 = p95 = p99 = 0.0

    return RunResult(
        mode=mode,
        queries=timings,
        ingest_wall_clock_s=(
            round(ingest_wall_clock_s, 2) if ingest_wall_clock_s else None
        ),
        p50_ms=round(p50, 2),
        p95_ms=round(p95, 2),
        p99_ms=round(p99, 2),
        error_count=error_count,
    )


def _print_summary(result: RunResult) -> None:
    print(f"\n  Summary ({result.mode})")
    print(f"  {'-' * 60}")
    print(f"  P50:  {result.p50_ms:>8.2f} ms")
    print(f"  P95:  {result.p95_ms:>8.2f} ms")
    print(f"  P99:  {result.p99_ms:>8.2f} ms")
    if result.ingest_wall_clock_s is not None:
        print(f"  Ingest:  {result.ingest_wall_clock_s:>5.2f} s")
    if result.error_count:
        print(f"  Errors:  {result.error_count}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Async chunking responsiveness experiment"
    )
    parser.add_argument(
        "--mode",
        choices=["idle-baseline", "under-load"],
        required=True,
    )
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--cadence-ms", type=int, default=100)
    parser.add_argument(
        "--ingest-path",
        type=str,
        default=None,
        help="Directory/file for under-load mode",
    )
    parser.add_argument(
        "--output", type=str, default="results.json",
        help="JSON output filename (relative to experiment dir)",
    )
    args = parser.parse_args()

    if args.mode == "idle-baseline":
        result = asyncio.run(_run_idle_baseline(args))
    else:
        result = asyncio.run(_run_under_load(args))

    _print_summary(result)

    output_path = EXPERIMENT_DIR / args.output
    with open(output_path, "w") as f:
        json.dump(asdict(result), f, indent=2)
    print(f"\n  Raw results saved to: {output_path}")


if __name__ == "__main__":
    main()
