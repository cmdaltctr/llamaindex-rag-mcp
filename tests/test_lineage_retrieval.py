"""Red-first retrieval tests for stable lineage propagation (task 1.7).

Pins ``openspec/changes/add-stable-source-chunk-lineage``: public search
results expose ``source_id``, ``source_version``, ``chunk_id``,
``source_chunk_index``, and ``source_chunk_count`` from stored metadata across
dense, BM25/hybrid fusion, reranker success, and reranker failure paths, while
the attempt-specific vector-row ``id`` stays hidden from ordinary results.

No lineage implementation exists yet, so the red run fails on the missing
result fields (``KeyError``) per scenario.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from rag_mcp.core.ingestion import ingest_path_async
from rag_mcp.core.retrieval import search
from rag_mcp.core.retrieval.pipeline import RERANK_SCORE_KIND

_COLLECTION = "lineage_docs"
_FILE_TEXT = "lineage sentinel paragraph about quantum foxes " * 240
_LINEAGE_FIELDS = (
    "source_id",
    "source_version",
    "chunk_id",
    "source_chunk_index",
    "source_chunk_count",
)


def _expected_source_id(canonical_file_path: str) -> str:
    """Return the spec-pinned source_id digest (kept inline for independence)."""
    return "src_" + hashlib.sha256(("file\0" + canonical_file_path).encode("utf-8")).hexdigest()


async def _ingest_lineage_source(tmp_path: Path) -> Path:
    """Ingest one multi-chunk source into the lineage collection."""
    source = tmp_path / "lineage-source.txt"
    source.write_text(_FILE_TEXT, encoding="utf-8")
    result = await ingest_path_async(str(source), collection_name=_COLLECTION)
    assert result["status"] == "ok"
    return source


def _search_kwargs(**extra) -> dict:
    """Return permissive search defaults so every chunk stays eligible."""
    kwargs = {
        "collection_name": _COLLECTION,
        "similarity_threshold": 0.0,
        "top_k": 50,
    }
    kwargs.update(extra)
    return kwargs


def _assert_lineage(result: dict) -> None:
    """Assert one public result carries the full stable lineage fields."""
    metadata = result["metadata"]
    for field in _LINEAGE_FIELDS:
        assert result[field] == metadata[field]
    assert "id" not in result


class _StubReranker:
    """Stub reranker emulating load-failure semantics on demand."""

    backend_name = "stub"

    def __init__(self, *, succeeds: bool) -> None:
        self.succeeds = succeeds

    def rerank(self, query, results, top_k):  # noqa: ANN001, ARG002
        """Rescore deterministically; failed stubs leave ``_reranked`` False."""
        for position, result in enumerate(results):
            result["score"] = 1.0 - position * 0.01
            result["_reranked"] = self.succeeds
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:top_k]


async def test_dense_results_expose_lineage_and_hide_row_id(tmp_path: Path) -> None:
    """Spec: dense results carry stable lineage without the vector-row id.

    Context assembly (fix-retrieval-freshness-and-context-assembly-2)
    merges adjacent chunks of one source into single rows by default, so
    the constituent coverage is read through ``chunk_ids`` on merged rows:
    every stored chunk of the source is still represented exactly once.
    """
    source = await _ingest_lineage_source(tmp_path)
    expected_sid = _expected_source_id(str(source))

    results = search("quantum foxes", hybrid=False, rerank=False, **_search_kwargs())

    assert results
    represented: list[str] = []
    for result in results:
        _assert_lineage(result)
        assert result["source_id"] == expected_sid
        represented.extend(result.get("chunk_ids", [result["chunk_id"]]))
    assert len(set(represented)) == len(represented), "a chunk was returned twice"
    assert len(represented) >= 2, "the source must produce multiple represented chunks"
    assert all(result["source_chunk_count"] == len(represented) for result in results)
    assert results[0]["source_chunk_index"] == 0


async def test_hybrid_bm25_results_expose_identical_lineage(tmp_path: Path) -> None:
    """Spec: one chunk returned by dense and BM25 shows identical lineage."""
    await _ingest_lineage_source(tmp_path)

    dense = search("quantum foxes", hybrid=False, rerank=False, **_search_kwargs())
    hybrid = search("quantum foxes", hybrid=True, rerank=False, **_search_kwargs())

    assert dense and hybrid
    for result in hybrid:
        _assert_lineage(result)
    dense_by_chunk = {result["chunk_id"]: result for result in dense}
    common = [cid for cid in (result["chunk_id"] for result in hybrid) if cid in dense_by_chunk]
    assert common, "no chunk was returned by both the dense and BM25 paths"
    for chunk_id in common:
        hybrid_row = next(result for result in hybrid if result["chunk_id"] == chunk_id)
        for field in _LINEAGE_FIELDS:
            assert hybrid_row[field] == dense_by_chunk[chunk_id][field]


async def test_successful_reranker_preserves_lineage(tmp_path: Path) -> None:
    """Spec: reranked results keep lineage, gain the reranker score kind."""
    await _ingest_lineage_source(tmp_path)

    results = search(
        "quantum foxes",
        rerank=True,
        reranker=_StubReranker(succeeds=True),
        **_search_kwargs(),
    )

    assert results
    for result in results:
        _assert_lineage(result)
        assert result["reranked"] is True
        assert result["score_kind"] == RERANK_SCORE_KIND


async def test_failed_reranker_preserves_lineage(tmp_path: Path) -> None:
    """Spec: a failed reranker keeps lineage and hides the vector-row id."""
    await _ingest_lineage_source(tmp_path)

    results = search(
        "quantum foxes",
        rerank=True,
        reranker=_StubReranker(succeeds=False),
        **_search_kwargs(),
    )

    assert results
    for result in results:
        _assert_lineage(result)
        assert result["reranked"] is False


async def test_source_id_filter_limits_results_to_one_source(tmp_path: Path) -> None:
    """Spec: an existing metadata filter on source_id needs no new query API."""
    source = await _ingest_lineage_source(tmp_path)
    expected_sid = _expected_source_id(str(source))

    results = search(
        "quantum foxes",
        rerank=False,
        metadata_filter={"source_id": expected_sid},
        **_search_kwargs(),
    )

    assert results
    assert {result["source_id"] for result in results} == {expected_sid}


async def test_chunk_id_filter_selects_exactly_one_row(tmp_path: Path) -> None:
    """Spec: an existing metadata filter on chunk_id selects one chunk."""
    await _ingest_lineage_source(tmp_path)
    all_results = search("quantum foxes", hybrid=False, rerank=False, **_search_kwargs())
    target_chunk_id = all_results[0]["chunk_id"]

    single = search(
        "quantum foxes",
        hybrid=False,
        rerank=False,
        metadata_filter={"chunk_id": target_chunk_id},
        **_search_kwargs(),
    )

    assert len(single) == 1
    _assert_lineage(single[0])
    assert single[0]["chunk_id"] == target_chunk_id
