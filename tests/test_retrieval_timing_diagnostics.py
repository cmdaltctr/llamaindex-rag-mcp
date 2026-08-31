"""Red-first contract tests for per-stage retrieval timing diagnostics.

Pins ``openspec/changes/complete-observable-surface`` Thread B tasks 3.1-3.8:
the ``timings`` mapping on each result row when diagnostics are enabled.
The tests exercise the real retrieval pipeline against a stub store so the
timing instrumentation inside ``_dense_query_rows``, ``_hybrid_query_rows``,
and ``search()`` is actually driven.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest

# ── Stub store supporting dense + BM25 sparse paths ────────────────────


def _full_metadata() -> dict:
    """Return a fully-populated lineage metadata row."""
    return {
        "source_id": "src_stable_001",
        "source_version": "2026-08-31T00:00:00Z",
        "chunk_id": "chunk_001",
        "source_chunk_index": 0,
        "source_chunk_count": 3,
        "file_path": "/abs/path/to/doc.txt",
        "page_label": None,
    }


class _StubSearchStore:
    """Minimal store satisfying dense query, BM25 sparse, and listing seams."""

    def __init__(self, text: str = "query text content for matching") -> None:
        self._text = text
        self._meta = _full_metadata()

    @property
    def cache_identity(self) -> object:
        return self

    def count(self, collection_name: str) -> int:
        return 1

    def query_dense(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int,
        where: dict | None = None,
    ) -> list[dict]:
        return [
            {
                "id": "row_001",
                "score": 0.95,
                "score_kind": "dense_similarity_v1",
                "document": self._text,
                "metadata": dict(self._meta),
            }
        ]

    def iter_documents(
        self, collection_name: str, page_size: int | None = None
    ) -> Iterator[tuple[str, str, dict]]:
        yield ("row_001", self._text, dict(self._meta))

    def iter_metadatas(
        self, collection_name: str, page_size: int | None = None
    ) -> Iterator[dict | None]:
        yield dict(self._meta)

    def get_generation(self, collection_name: str) -> int:
        return 0

    def bump_generation(self, collection_name: str) -> None:
        pass


class _StubReranker:
    """A reranker that succeeds and reports a backend name."""

    backend_name = "stub"
    last_failure_reason: str | None = None

    def rerank(self, query: str, results: list[dict], top_k: int) -> list[dict]:
        for r in results:
            r["score"] = 0.5
            r["_reranked"] = True
        return results[:top_k]


class _FailingReranker:
    """A reranker that fails, triggering the re-query path."""

    backend_name = "stub"
    last_failure_reason = "inference failed"

    def rerank(self, query: str, results: list[dict], top_k: int) -> list[dict]:
        for r in results:
            r["_reranked"] = False
        return results


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_retrieval_caches() -> Iterator[None]:
    """Clear the embedding LRU and BM25 caches for deterministic tests."""
    from rag_mcp.core.retrieval.dense import _cached_query_embedding
    from rag_mcp.core.retrieval.sparse import BM25SparseRetriever

    _cached_query_embedding.cache_clear()
    BM25SparseRetriever._cache.clear()
    yield
    _cached_query_embedding.cache_clear()
    BM25SparseRetriever._cache.clear()


def _search(
    *,
    hybrid: bool = False,
    rerank: bool = False,
    diagnostics: bool = False,
    store: Any | None = None,
    reranker: Any | None = None,
    query: str = "query text",
    similarity_threshold: float | None = None,
) -> list[dict]:
    """Run a search with default stubs and return results."""
    from rag_mcp.core.retrieval import search
    from rag_mcp.core.settings import EffectiveSettings

    return search(
        query,
        top_k=5,
        rerank=rerank,
        hybrid=hybrid,
        store=store or _StubSearchStore(),
        effective_settings=EffectiveSettings(),
        include_diagnostics=diagnostics,
        reranker=reranker,
        similarity_threshold=similarity_threshold,
    )


# ── Task 3.1: hybrid search reports all stage durations ───────────────


class TestHybridTimingDiagnostics:
    """A hybrid search with diagnostics reports every retrieval stage."""

    def test_hybrid_search_timings_on_every_row(self) -> None:
        """Each result carries a ``timings`` mapping with stage durations.

        The mapping contains embedding, dense, sparse, and fusion durations.
        Every reported duration is a non-negative number of seconds.
        """
        results = _search(
            hybrid=True,
            rerank=False,
            diagnostics=True,
        )

        assert len(results) > 0, "Expected at least one result"
        for row in results:
            assert "timings" in row, (
                f"Result row missing 'timings' field. Keys: {sorted(row.keys())}"
            )
            timings = row["timings"]
            assert isinstance(timings, dict), f"timings is {type(timings).__name__}, not dict"
            for stage in ("embedding_seconds", "dense_seconds", "sparse_seconds", "fusion_seconds"):
                assert stage in timings, (
                    f"timings missing stage '{stage}'. Stages present: {sorted(timings.keys())}"
                )
                assert isinstance(timings[stage], (int, float)), (
                    f"timings['{stage}'] is {type(timings[stage]).__name__}, not a number"
                )
                assert timings[stage] >= 0, (
                    f"timings['{stage}'] is {timings[stage]}, expected non-negative"
                )


# ── Task 3.2: dense-only search omits sparse and fusion ───────────────


class TestDenseOnlyTimingOmitsSparseFusion:
    """A dense-only search does not report sparse or fusion stages."""

    def test_dense_only_omits_sparse_and_fusion_keys(self) -> None:
        """The timings mapping contains no sparse or fusion entry.

        Absent entries are omitted rather than reported as zero.
        """
        results = _search(
            hybrid=False,
            rerank=False,
            diagnostics=True,
        )

        assert len(results) > 0
        for row in results:
            assert "timings" in row
            timings = row["timings"]
            assert "sparse_seconds" not in timings, (
                f"Dense-only search should not report sparse_seconds. "
                f"Stages present: {sorted(timings.keys())}"
            )
            assert "fusion_seconds" not in timings, (
                f"Dense-only search should not report fusion_seconds. "
                f"Stages present: {sorted(timings.keys())}"
            )
            # Embedding and dense should still be present.
            assert "embedding_seconds" in timings
            assert "dense_seconds" in timings


# ── Task 3.3: rerank key presence follows the rerank decision ──────────


class TestRerankTimingPresence:
    """The rerank stage duration appears only when the reranker ran."""

    def test_non_reranked_search_omits_rerank_key(self) -> None:
        """A search with no reranking omits the rerank entry."""
        results = _search(
            hybrid=False,
            rerank=False,
            diagnostics=True,
        )

        assert len(results) > 0
        for row in results:
            timings = row["timings"]
            assert "rerank_seconds" not in timings, (
                f"Non-reranked search should not report rerank_seconds. "
                f"Stages present: {sorted(timings.keys())}"
            )

    def test_reranked_search_includes_rerank_key(self) -> None:
        """A search that runs the reranker includes the rerank entry."""
        results = _search(
            hybrid=False,
            rerank=True,
            diagnostics=True,
            reranker=_StubReranker(),
        )

        assert len(results) > 0
        for row in results:
            timings = row["timings"]
            assert "rerank_seconds" in timings, (
                f"Reranked search should report rerank_seconds. "
                f"Stages present: {sorted(timings.keys())}"
            )
            assert timings["rerank_seconds"] >= 0


# ── Task 3.4: diagnostics off → no timings, default shape ─────────────


class TestDiagnosticsOffOmitsTimings:
    """Without diagnostics, no timings field appears and shape is unchanged."""

    def test_no_timings_without_diagnostics(self) -> None:
        """A search without diagnostics carries no ``timings`` field."""
        results = _search(
            hybrid=True,
            rerank=True,
            diagnostics=False,
            reranker=_StubReranker(),
        )

        assert len(results) > 0
        for row in results:
            assert "timings" not in row, (
                f"timings should not appear without diagnostics. Keys: {sorted(row.keys())}"
            )

    def test_default_shape_matches_non_diagnostics_exactly(self) -> None:
        """The default result shape is unchanged from the pre-timing shape."""
        results = _search(hybrid=False, rerank=False, diagnostics=False)

        assert len(results) > 0
        expected_keys = {
            "score",
            "score_kind",
            "source",
            "page_label",
            "text",
            "reranked",
            "metadata",
            "source_id",
            "source_version",
            "chunk_id",
            "source_chunk_index",
            "source_chunk_count",
        }
        for row in results:
            assert set(row.keys()) == expected_keys, (
                f"Default result keys mismatch. "
                f"Expected: {sorted(expected_keys)}, "
                f"Got: {sorted(row.keys())}"
            )


# ── Task 3.5: timing is measurement-only (identical results) ──────────


class TestTimingIsMeasurementOnly:
    """Enabling diagnostics does not change retrieval outcomes."""

    def test_identical_results_with_and_without_diagnostics(self) -> None:
        """Both runs return the same identities, order, and scores."""
        query = "query text"
        store1 = _StubSearchStore()
        store2 = _StubSearchStore()

        off = _search(query=query, hybrid=True, rerank=False, diagnostics=False, store=store1)
        on = _search(query=query, hybrid=True, rerank=False, diagnostics=True, store=store2)

        assert len(off) == len(on)
        for off_row, on_row in zip(off, on, strict=True):
            assert off_row["source"] == on_row["source"]
            assert off_row["score"] == on_row["score"]
            assert off_row["text"] == on_row["text"]


# ── Task 3.6: cached embedding is not re-fetched ───────────────────────


class TestCachedEmbeddingTiming:
    """A cached query embedding is not re-fetched but still reports a duration."""

    def test_repeated_query_calls_provider_once_but_reports_duration_both_times(self) -> None:
        """An identical query embedded earlier is served from cache.

        The embedding provider MUST NOT be called a second time, but an
        embedding duration MUST still be reported on the second call
        because the stage ran and served from cache (design D9: count
        provider calls via LRU cache_info, do not compare durations).
        """
        from rag_mcp.core.retrieval.dense import _cached_query_embedding

        # The autouse _clear_retrieval_caches fixture already cleared the
        # LRU cache before this test, so the first search is a guaranteed
        # cache miss.
        first = _search(query="query text", hybrid=False, rerank=False, diagnostics=True)
        assert len(first) > 0

        info_after_first = _cached_query_embedding.cache_info()
        misses_after_first = info_after_first.misses
        assert misses_after_first >= 1, "Provider should have been called at least once"

        # Second search — same query, should be a cache hit.
        second = _search(query="query text", hybrid=False, rerank=False, diagnostics=True)
        assert len(second) > 0

        info_after_second = _cached_query_embedding.cache_info()

        assert info_after_second.misses == misses_after_first, (
            f"Embedding provider was called again on the second identical "
            f"query (misses went from {misses_after_first} to "
            f"{info_after_second.misses}). The LRU cache should have "
            f"served the second query."
        )
        assert info_after_second.hits > 0, "Expected at least one cache hit"

        # An embedding duration must still be reported on the second call.
        assert "embedding_seconds" in second[0]["timings"], (
            "Second search should still report embedding_seconds even on "
            "a cache hit, because the stage ran and served from cache."
        )


# ── Task 3.7: failed-rerank re-query sums both executions ─────────────


class TestFailedRerankReQueryTimingSum:
    """A failed rerank re-query accumulates both executions' durations."""

    def test_re_query_sums_dense_sparse_fusion_and_reports_rerank(self) -> None:
        """Dense, sparse, and fusion durations are the sum of both executions.

        A rerank duration is present because the reranker ran (and failed).
        Driven with the stub reranker pattern from test_hybrid_retrieval.py.
        """
        results = _search(
            hybrid=True,
            rerank=True,
            diagnostics=True,
            reranker=_FailingReranker(),
            similarity_threshold=0.3,
        )

        assert len(results) > 0
        for row in results:
            timings = row["timings"]
            # All stages that ran (twice for dense/sparse/fusion, once for rerank).
            for stage in ("embedding_seconds", "dense_seconds", "sparse_seconds", "fusion_seconds"):
                assert stage in timings, (
                    f"timings missing '{stage}' after re-query. Stages: {sorted(timings.keys())}"
                )
                assert timings[stage] >= 0
            # Rerank ran (and failed), so its duration must be present.
            assert "rerank_seconds" in timings, (
                f"timings missing 'rerank_seconds' after failed rerank. "
                f"Stages: {sorted(timings.keys())}"
            )
            assert timings["rerank_seconds"] >= 0


# ── Task 3.8: zero results → no timings ────────────────────────────────


class TestZeroResultsNoTimings:
    """A search returning no results reports no timings."""

    def test_empty_result_carries_no_timings(self) -> None:
        """An empty result list has no rows, so no timings are returned.

        This pins the documented boundary: timings travel on result rows.
        """
        from rag_mcp.core.retrieval import search
        from rag_mcp.core.settings import EffectiveSettings

        empty_store = MagicMock()
        empty_store.count.return_value = 0

        results = search(
            "query text",
            top_k=5,
            hybrid=True,
            rerank=True,
            store=empty_store,
            effective_settings=EffectiveSettings(),
            include_diagnostics=True,
            reranker=_StubReranker(),
        )

        assert results == []
