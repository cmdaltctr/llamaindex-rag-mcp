"""Unit tests for the chunk-lineage-navigation capability (stage 4).

Pins ``openspec/changes/fix-retrieval-freshness-and-context-assembly-2``
capability ``chunk-lineage-navigation`` against the real store
implementations: neighbour lookup with clamping, source and version
isolation, edge handling, inert rows without lineage, bounded reads,
contiguity decisions, and span reconstruction.  The suite is
parametrised over ``chroma`` (in-memory, skipped without the optional
extra) and ``lancedb`` (isolated on-disk database under ``tmp_path``),
mirroring the differential pattern of ``tests/test_vectordb_contract.py``.
"""

from __future__ import annotations

import copy
import inspect
from pathlib import Path
from typing import Any

import pytest

from rag_mcp.core.retrieval.lineage import is_adjacent, neighbours, span
from rag_mcp.core.vectordb.base import VectorStore
from rag_mcp.core.vectordb.identity import EmbeddingIdentity
from rag_mcp.core.vectordb.lancedb import LanceVectorStore

_COLLECTION = "lineage_nav"
_ALPHA = "src_alpha"
_BETA = "src_beta"
_V1 = "ver_one"
_V2 = "ver_two"
_PRECOMPUTED_IDENTITY = EmbeddingIdentity(provider="test", model="mock")


def _store_class(backend: str) -> type[VectorStore]:
    """Resolve a concrete store class lazily (chromadb may be absent)."""
    if backend == "lancedb":
        return LanceVectorStore
    from rag_mcp.core.vectordb.chroma import ChromaVectorStore

    return ChromaVectorStore


@pytest.fixture(params=["chroma", "lancedb"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> VectorStore:
    """Return a fresh store for each backend under test.

    ``chroma`` relies on the in-memory EphemeralClient monkeypatched by
    ``conftest._patch_chromadb`` so no disk I/O occurs, and skips when
    the optional chroma extra is absent.  ``lancedb`` points at an
    isolated database under ``tmp_path``.
    """
    if request.param == "chroma":
        pytest.importorskip(
            "chromadb",
            reason="chroma extra not installed; runs in the chroma-extra CI job",
        )
        return _store_class("chroma")()
    return LanceVectorStore(uri=str(tmp_path / "lancedb"))


# ── Seed data ─────────────────────────────────────────────────────────


def _text(source_id: str, version: str, index: int) -> str:
    """Return the unique stored text of one seeded chunk."""
    token = f"{source_id[-4:]}{version[-3:]}{index}"
    return f"{source_id} {version} chunk {index} carries unique token {token}"


def _meta(
    source_id: str,
    version: str,
    index: int,
    count: int,
    *,
    attempt: str = "att_one",
) -> dict[str, Any]:
    """Return persisted-style lineage metadata for one seeded chunk."""
    return {
        "file_path": f"/data/{source_id}.txt",
        "source_id": source_id,
        "source_version": version,
        "chunk_id": f"chk_{source_id}_{version}_{index}",
        "source_chunk_index": index,
        "source_chunk_count": count,
        "source_attempt": attempt,
    }


def _seed(store: VectorStore, collection: str = _COLLECTION) -> None:
    """Write an interleaved multi-source, multi-version collection.

    Storage order interleaves the sources and versions so any lookup
    that walks storage order instead of filtering would cross a
    boundary.  One row carries no lineage at all, standing in for an
    experiment precomputed row.
    """
    chunks: list[tuple[str, str, int, int]] = [
        (_ALPHA, _V1, 0, 5),
        (_BETA, _V1, 0, 3),
        (_ALPHA, _V2, 0, 5),
        (_ALPHA, _V1, 1, 5),
        (_BETA, _V1, 1, 3),
        (_ALPHA, _V2, 1, 5),
        (_ALPHA, _V1, 2, 5),
        (_BETA, _V1, 2, 3),
        (_ALPHA, _V2, 2, 5),
        (_ALPHA, _V1, 3, 5),
        (_ALPHA, _V2, 3, 5),
        (_ALPHA, _V1, 4, 5),
        (_ALPHA, _V2, 4, 5),
    ]
    ids = [f"row_{source}_{version}_{index}" for source, version, index, _ in chunks]
    documents = [_text(source, version, index) for source, version, index, _ in chunks]
    metadatas = [
        _meta(source, version, index, count, attempt="att_two" if version == _V2 else "att_one")
        for source, version, index, count in chunks
    ]
    # One experiment precomputed row without any lineage metadata.
    ids.append("row_experiment")
    documents.append("experiment precomputed row with no lineage")
    metadatas.append({"file_path": "/exp/row.bin"})
    embeddings = [[float(index % 2), 1.0] for index in range(len(ids))]
    store.upsert_precomputed(
        collection,
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
        embedding_identity=_PRECOMPUTED_IDENTITY,
    )


def _result_row(
    source_id: str,
    version: str,
    index: int,
    count: int,
    *,
    drop_top_level_lineage: bool = False,
) -> dict[str, Any]:
    """Build a retrieval-shaped result row for one seeded chunk."""
    meta = _meta(source_id, version, index, count)
    row: dict[str, Any] = {
        "id": f"row_{source_id}_{version}_{index}",
        "score": 0.9,
        "score_kind": "dense_cosine",
        "source": meta["file_path"],
        "text": _text(source_id, version, index),
        "metadata": meta,
        "reranked": False,
    }
    if not drop_top_level_lineage:
        row.update(
            {
                "source_id": meta["source_id"],
                "source_version": meta["source_version"],
                "chunk_id": meta["chunk_id"],
                "source_chunk_index": meta["source_chunk_index"],
                "source_chunk_count": meta["source_chunk_count"],
            }
        )
    return row


def _experiment_row() -> dict[str, Any]:
    """Build a retrieval-shaped row lacking every lineage field."""
    return {
        "id": "row_experiment",
        "score": 0.5,
        "score_kind": "dense_cosine",
        "source": "/exp/row.bin",
        "text": "experiment precomputed row with no lineage",
        "metadata": {"file_path": "/exp/row.bin"},
        "reranked": False,
    }


def _spy_reads(store: VectorStore, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Count filtered reads and forbid whole-collection scans.

    Wraps ``iter_filtered_documents`` to record every row materialised
    and every where clause issued, and replaces ``iter_documents`` with
    a hard failure so a collection scan cannot pass unnoticed.
    """
    calls: dict[str, Any] = {"rows": 0, "wheres": []}
    original = store.iter_filtered_documents

    def _counting_filtered(collection_name: str, where: dict, page_size: int | None = None):
        calls["wheres"].append(dict(where))
        for row in original(collection_name, where, page_size):
            calls["rows"] += 1
            yield row

    def _forbidden_scan(collection_name: str, page_size: int | None = None):
        raise AssertionError("lineage navigation must never scan the collection")

    monkeypatch.setattr(store, "iter_filtered_documents", _counting_filtered)
    monkeypatch.setattr(store, "iter_documents", _forbidden_scan)
    return calls


# ── Contiguity (Requirement: Contiguity is decidable) ────────────────


class TestIsAdjacent:
    """``is_adjacent`` decides contiguity from lineage metadata alone."""

    def test_consecutive_chunks_of_one_source_version_are_adjacent(self) -> None:
        """Scenario: two chunks sharing a source with indices i and i+1."""
        assert is_adjacent(_meta(_ALPHA, _V1, 2, 5), _meta(_ALPHA, _V1, 3, 5)) is True

    def test_adjacency_is_symmetric(self) -> None:
        """The order of the pair must not change the decision."""
        assert is_adjacent(_meta(_ALPHA, _V1, 3, 5), _meta(_ALPHA, _V1, 2, 5)) is True

    def test_non_consecutive_indices_are_not_adjacent(self) -> None:
        """Only indices differing by exactly one are adjacent."""
        assert is_adjacent(_meta(_ALPHA, _V1, 0, 5), _meta(_ALPHA, _V1, 2, 5)) is False

    def test_chunks_of_different_sources_are_never_adjacent(self) -> None:
        """Scenario: different source_id values, whatever their indices."""
        assert is_adjacent(_meta(_ALPHA, _V1, 1, 5), _meta(_BETA, _V1, 2, 3)) is False
        assert is_adjacent(_meta(_BETA, _V1, 0, 3), _meta(_ALPHA, _V1, 1, 5)) is False

    def test_chunks_of_different_source_versions_are_never_adjacent(self) -> None:
        """Scenario: same source_id, different source_version values."""
        assert is_adjacent(_meta(_ALPHA, _V1, 2, 5), _meta(_ALPHA, _V2, 3, 5)) is False

    def test_rows_without_lineage_are_inert_and_never_raise(self) -> None:
        """Rows lacking lineage cannot be adjacent to anything."""
        no_lineage = {"file_path": "/exp/row.bin"}
        assert is_adjacent(no_lineage, _meta(_ALPHA, _V1, 2, 5)) is False
        assert is_adjacent(_meta(_ALPHA, _V1, 2, 5), no_lineage) is False
        assert is_adjacent({}, {}) is False

    def test_indices_outside_the_chunk_count_are_not_adjacent(self) -> None:
        """Corrupt lineage clamped by source_chunk_count is inert."""
        assert is_adjacent(_meta(_ALPHA, _V1, 4, 5), _meta(_ALPHA, _V1, 5, 5)) is False

    def test_accepts_result_rows_and_bare_metadata_dicts(self) -> None:
        """Both retrieval result rows and metadata dicts decide identically."""
        as_result = _result_row(_ALPHA, _V1, 1, 5)
        as_meta = _meta(_ALPHA, _V1, 2, 5)
        assert is_adjacent(as_result, as_meta) is True


# ── Neighbour lookup (Requirement: neighbours from persisted metadata) ─


class TestNeighbours:
    """``neighbours`` resolves neighbour chunks through filtered reads."""

    def test_window_returns_both_sides_excluding_self_in_ascending_order(
        self, store: VectorStore
    ) -> None:
        """Scenario: neighbours of a chunk with window w."""
        _seed(store)
        found = neighbours([_result_row(_ALPHA, _V1, 2, 5)], store, _COLLECTION, 2)
        assert [row["source_chunk_index"] for row in found] == [0, 1, 3, 4]
        assert [row["text"] for row in found] == [
            _text(_ALPHA, _V1, 0),
            _text(_ALPHA, _V1, 1),
            _text(_ALPHA, _V1, 3),
            _text(_ALPHA, _V1, 4),
        ]

    def test_neighbour_lookup_crosses_no_source_boundary(self, store: VectorStore) -> None:
        """Scenario: interleaved sources never leak into each other."""
        _seed(store)
        found = neighbours([_result_row(_ALPHA, _V1, 2, 5)], store, _COLLECTION, 1)
        assert [row["source_chunk_index"] for row in found] == [1, 3]
        assert {row["source_id"] for row in found} == {_ALPHA}
        assert _text(_BETA, _V1, 1) not in {row["text"] for row in found}

    def test_neighbour_lookup_crosses_no_version_boundary(self, store: VectorStore) -> None:
        """Chunks of another version share indices but are never neighbours."""
        _seed(store)
        found = neighbours([_result_row(_ALPHA, _V1, 2, 5)], store, _COLLECTION, 2)
        assert {row["source_version"] for row in found} == {_V1}
        assert _text(_ALPHA, _V2, 1) not in {row["text"] for row in found}
        assert _text(_ALPHA, _V2, 3) not in {row["text"] for row in found}

    def test_edges_of_a_source_return_only_the_existing_side(self, store: VectorStore) -> None:
        """Scenario: first and last chunks, clamped, without error."""
        _seed(store)
        first = neighbours([_result_row(_ALPHA, _V1, 0, 5)], store, _COLLECTION, 2)
        assert [row["source_chunk_index"] for row in first] == [1, 2]
        last = neighbours([_result_row(_ALPHA, _V1, 4, 5)], store, _COLLECTION, 2)
        assert [row["source_chunk_index"] for row in last] == [2, 3]
        # A window wider than the source clamps on both sides.
        narrow = neighbours([_result_row(_BETA, _V1, 1, 3)], store, _COLLECTION, 5)
        assert [row["source_chunk_index"] for row in narrow] == [0, 2]

    def test_rows_without_lineage_are_inert_and_the_caller_keeps_them(
        self, store: VectorStore
    ) -> None:
        """Scenario: rows lacking lineage are skipped, never raised over."""
        _seed(store)
        rows = [_experiment_row(), _result_row(_ALPHA, _V1, 2, 5)]
        before = copy.deepcopy(rows)
        found = neighbours(rows, store, _COLLECTION, 1)
        assert [row["source_chunk_index"] for row in found] == [1, 3]
        assert rows == before, "the retrieved rows must be returned to the caller unchanged"
        assert rows[0]["id"] == "row_experiment"

    def test_row_missing_only_the_index_is_inert(self, store: VectorStore) -> None:
        """A row with source identity but no index cannot be expanded."""
        _seed(store)
        partial = _result_row(_ALPHA, _V1, 2, 5)
        partial.pop("source_chunk_index")
        partial["metadata"].pop("source_chunk_index")
        assert neighbours([partial], store, _COLLECTION, 1) == []

    def test_lineage_is_read_from_nested_metadata_when_top_level_absent(
        self, store: VectorStore
    ) -> None:
        """Raw store rows carrying lineage inside metadata also expand."""
        _seed(store)
        row = _result_row(_ALPHA, _V1, 2, 5, drop_top_level_lineage=True)
        found = neighbours([row], store, _COLLECTION, 1)
        assert [row["source_chunk_index"] for row in found] == [1, 3]

    def test_lookup_is_bounded_by_window_and_result_count(
        self, store: VectorStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Scenario: rows read are bounded by window and result count."""
        _seed(store)
        calls = _spy_reads(store, monkeypatch)
        rows = [_result_row(_ALPHA, _V1, 2, 5), _result_row(_ALPHA, _V1, 4, 5)]
        window = 1
        found = neighbours(rows, store, _COLLECTION, window)
        assert [row["source_chunk_index"] for row in found] == [1, 3]
        assert calls["rows"] <= 2 * window * len(rows)
        assert calls["wheres"], "neighbour lookup must read through the filtered contract"
        for where in calls["wheres"]:
            assert where, "an empty where would scan the collection"
            assert where["source_id"] == _ALPHA
            assert where["source_version"] == _V1

    def test_zero_window_reads_nothing(
        self, store: VectorStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A window of zero means no expansion and no reads."""
        _seed(store)
        calls = _spy_reads(store, monkeypatch)
        assert neighbours([_result_row(_ALPHA, _V1, 2, 5)], store, _COLLECTION, 0) == []
        assert calls["rows"] == 0
        assert calls["wheres"] == []

    def test_multiple_rows_dedupe_and_exclude_retrieved_indices(self, store: VectorStore) -> None:
        """Overlapping windows dedupe; retrieved chunks are not re-fetched."""
        _seed(store)
        rows = [_result_row(_ALPHA, _V1, 1, 5), _result_row(_ALPHA, _V1, 3, 5)]
        found = neighbours(rows, store, _COLLECTION, 2)
        assert [row["source_chunk_index"] for row in found] == [0, 2, 4]

    def test_sources_stay_in_first_appearance_order(self, store: VectorStore) -> None:
        """Each source's neighbours ascend; sources follow the result rows."""
        _seed(store)
        rows = [_result_row(_BETA, _V1, 1, 3), _result_row(_ALPHA, _V1, 0, 5)]
        found = neighbours(rows, store, _COLLECTION, 1)
        assert [row["source_id"] for row in found] == [_BETA, _BETA, _ALPHA]
        assert [row["source_chunk_index"] for row in found] == [0, 2, 1]

    def test_absent_collection_returns_nothing(self, store: VectorStore) -> None:
        """Neighbour lookup on a missing collection is empty, not an error."""
        found = neighbours([_result_row(_ALPHA, _V1, 2, 5)], store, "nope", 1)
        assert found == []


# ── Span reconstruction ───────────────────────────────────────────────


class TestSpan:
    """``span`` reconstructs contiguous ranges of one source version."""

    def test_span_returns_the_contiguous_range_in_ascending_order(self, store: VectorStore) -> None:
        """A middle range of one source version comes back in order."""
        _seed(store)
        found = span(store, _COLLECTION, _ALPHA, _V1, 1, 3)
        assert [row["source_chunk_index"] for row in found] == [1, 2, 3]
        assert [row["text"] for row in found] == [
            _text(_ALPHA, _V1, 1),
            _text(_ALPHA, _V1, 2),
            _text(_ALPHA, _V1, 3),
        ]

    def test_span_clamps_to_the_source_chunk_count(self, store: VectorStore) -> None:
        """Scenario-bound clamping to [0, source_chunk_count)."""
        _seed(store)
        over = span(store, _COLLECTION, _ALPHA, _V1, 0, 99)
        assert [row["source_chunk_index"] for row in over] == [0, 1, 2, 3, 4]
        negative = span(store, _COLLECTION, _ALPHA, _V1, -5, 2)
        assert [row["source_chunk_index"] for row in negative] == [0, 1, 2]

    def test_full_span_is_the_ordered_chunk_set(self, store: VectorStore) -> None:
        """The full range reconstructs the source's ordered chunk set."""
        _seed(store)
        found = span(store, _COLLECTION, _BETA, _V1, 0, 2)
        assert [row["text"] for row in found] == [_text(_BETA, _V1, i) for i in range(3)]
        assert all(row["source_chunk_count"] == 3 for row in found)

    def test_span_of_one_version_excludes_the_other(self, store: VectorStore) -> None:
        """Same source, different version: no cross-version leakage."""
        _seed(store)
        found = span(store, _COLLECTION, _ALPHA, _V2, 0, 4)
        assert {row["source_version"] for row in found} == {_V2}
        assert [row["text"] for row in found] == [_text(_ALPHA, _V2, i) for i in range(5)]

    def test_span_of_an_absent_version_is_empty(self, store: VectorStore) -> None:
        """An unknown version yields nothing rather than an error."""
        _seed(store)
        assert span(store, _COLLECTION, _ALPHA, "ver_absent", 0, 4) == []

    def test_span_with_end_before_start_is_empty(self, store: VectorStore) -> None:
        """An inverted range yields nothing rather than an error."""
        _seed(store)
        assert span(store, _COLLECTION, _ALPHA, _V1, 3, 1) == []

    def test_span_reads_only_the_requested_range(
        self, store: VectorStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Span reads are bounded by the requested range, never a scan."""
        _seed(store)
        calls = _spy_reads(store, monkeypatch)
        span(store, _COLLECTION, _ALPHA, _V1, 0, 99)
        assert calls["rows"] == 5
        for where in calls["wheres"]:
            assert where["source_id"] == _ALPHA
            assert where["source_version"] == _V1


# ── Module boundaries (task 4.4) ──────────────────────────────────────


class TestModuleBoundaries:
    """The navigator stays store-neutral and retrieval-internal."""

    def test_lineage_module_imports_no_concrete_adapter(self) -> None:
        """No concrete adapter may be imported from the retrieval layer."""
        from rag_mcp.core.retrieval import lineage

        source = inspect.getsource(lineage)
        assert "lancedb" not in source.lower()
        assert "chroma" not in source.lower()

    def test_lineage_module_reads_through_the_filtered_contract(self) -> None:
        """The only store seam used is iter_filtered_documents."""
        from rag_mcp.core.retrieval import lineage

        source = inspect.getsource(lineage)
        assert "iter_filtered_documents" in source
        assert "iter_documents" not in source
