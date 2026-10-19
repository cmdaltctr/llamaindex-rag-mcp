"""Latency of the graph path against the direct path (unify-profiles, task 9.1).

See the "Latency check" section of the design.

The 15 recorded retrieval cases run through a built-in collection (``Engine.search``,
direct path) and through a duplicate user profile (graph path), 20 times each. The test
asserts equal rows and prints the median and the 95th percentile per query for each path
and the difference. It asserts no time limit, so a busy machine cannot fail it.

Run it with ``uv run pytest -m slow tests/unit/test_profile_dispatch_latency.py -s``.
"""

from __future__ import annotations

import statistics
import time
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.pipeline_parity.retrieval import harness
from tests.unit.test_engine_profiles_support import PROFILE, make_env, tagged_engine

from omrg.core.retrieval import registry

pytestmark = pytest.mark.slow

_CASES = harness.load_cases()
_REQUEST_KEYS = ("top_k", "similarity_threshold", "rerank", "fetch_k", "metadata_filter")
REPEATS = 20


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL__HYBRID_ENABLED", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__TOP_K"):
        monkeypatch.delenv(name, raising=False)


def _reranker(case: dict[str, Any], chunks: list[dict[str, Any]]) -> Any:
    mode = case.get("reranker", "success")
    if mode == "none":
        return None
    return harness.ParityReranker({c["id"]: c["rerank_score"] for c in chunks}, fail=mode == "fail")


def _percentile(values: list[float], fraction: float) -> float:
    """Return the nearest-rank percentile of ``values``."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(fraction * len(ordered)) - 1))]


def _timed(engine: Any, query: str, request: dict[str, Any]) -> tuple[list[dict], float]:
    start = time.perf_counter()
    rows = engine.search(query, collection_name="parity", **request)
    return rows, (time.perf_counter() - start) * 1000.0


def test_the_graph_path_costs_little_more_than_the_direct_path(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = harness.load_corpus()
    assert len(_CASES) == 15, "the design names 15 recorded retrieval cases"
    results: list[tuple[str, int, list[float], list[float]]] = []
    for index, case in enumerate(_CASES):
        chunks = [] if case.get("empty_collection") else corpus["chunks"]
        monkeypatch.setitem(registry._cache, "dense", harness.make_dense(chunks))
        settings = effective_settings(**case.get("settings", {}))
        env = make_env(
            tmp_path / f"case{index}", effective_settings, reranker=_reranker(case, chunks)
        )
        request = {k: case["search"][k] for k in _REQUEST_KEYS if k in case["search"]}
        query = case["search"].get("query", corpus["query"])
        builtin = tagged_engine(
            env, settings, chunks, "documents", reranker=_reranker(case, chunks)
        )
        user = tagged_engine(env, settings, chunks, PROFILE, reranker=_reranker(case, chunks))
        # One call each warms the BM25 index, the parsed graph and the reranker state.
        _timed(builtin, query, request)
        _timed(user, query, request)
        direct_ms: list[float] = []
        graph_ms: list[float] = []
        for _ in range(REPEATS):
            built_rows, built_time = _timed(builtin, query, request)
            user_rows, user_time = _timed(user, query, request)
            assert user_rows == built_rows, f"rows differ for case {case['name']}"
            row_count = len(built_rows)
            direct_ms.append(built_time)
            graph_ms.append(user_time)
        results.append((case["name"], row_count, direct_ms, graph_ms))
        builtin.close()
        user.close()

    print(f"\nDispatch latency, {REPEATS} runs per query and path (milliseconds)")
    header = (
        f"{'case':<38}{'rows':>5}{'direct p50':>11}{'direct p95':>11}"
        f"{'graph p50':>11}{'graph p95':>11}"
    )
    print(header + f"{'p50 diff':>10}{'p95 diff':>10}")
    median_diffs: list[float] = []
    p95_diffs: list[float] = []
    for name, rows, direct_ms, graph_ms in results:
        d50, d95 = statistics.median(direct_ms), _percentile(direct_ms, 0.95)
        g50, g95 = statistics.median(graph_ms), _percentile(graph_ms, 0.95)
        median_diffs.append(g50 - d50)
        p95_diffs.append(g95 - d95)
        print(
            f"{name:<38}{rows:>5}{d50:>11.2f}{d95:>11.2f}{g50:>11.2f}{g95:>11.2f}"
            f"{g50 - d50:>10.2f}{g95 - d95:>10.2f}"
        )
    print(
        f"{'median over the 15 queries':<38}{'':>49}"
        f"{statistics.median(median_diffs):>10.2f}{statistics.median(p95_diffs):>10.2f}"
    )
    print(
        f"{'mean over the 15 queries':<38}{'':>49}"
        f"{statistics.fmean(median_diffs):>10.2f}{statistics.fmean(p95_diffs):>10.2f}"
    )
