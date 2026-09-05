"""Native sparse backend contract: capability method and fallback surface.

Grows with ``implement-native-sparse-backend-strategy``:

- Phase 1 (task 1.2): the :class:`VectorStore` native sparse query
  capability — the ABC's explicit unsupported response, the canonical
  score kind, and the documented method shape.
- Phase 2: the LanceDB native FTS adapter (execution, normalisation,
  lifecycle) — see the sections below.
- Phase 3: the sparse-backend registry and composition-boundary
  resolution.

The unsupported-response tests pin the "fail honestly" contract: a
store without native sparse must raise, never return an empty ranking
that would read upstream as "no matches".
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from omrg.core.vectordb.base import VectorStore
from omrg.core.vectordb.score import DENSE_SCORE_KIND, NATIVE_SPARSE_SCORE_KIND


class _ThirdPartyStore(VectorStore):
    """Minimal concrete store: every abstract method is a stub.

    Stands in for older third-party stores that predate the native
    sparse capability — the ABC defaults must keep them instantiable
    while failing honestly on the new operation.
    """

    def create_collection(self, name: str) -> None: ...
    def collection_exists(self, name: str) -> bool:
        return False

    def delete_collection(self, name: str) -> None: ...
    def list_collections(self) -> list[str]:
        return []

    def write_nodes(self, nodes: list[Any], collection_name: str) -> None: ...
    def query_dense(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int,
        where: dict | None = None,
    ) -> list[dict]:
        return []

    def iter_metadatas(self, collection_name: str, page_size: int | None = None):
        return
        yield  # pragma: no cover - generator stub

    def fetch_all(self, collection_name: str, include: list[str]) -> dict | None:
        return None

    def iter_documents(self, collection_name: str, page_size: int | None = None):
        return
        yield  # pragma: no cover - generator stub

    def count(self, collection_name: str) -> int:
        return 0

    def count_where(self, collection_name: str, where: dict) -> int:
        return 0

    def delete_where(self, collection_name: str, where: dict) -> None: ...
    def get_collection_metadata(self, collection_name: str) -> dict | None:
        return None

    def update_collection_metadata(self, collection_name: str, metadata: dict) -> None: ...
    def bump_generation(self, collection_name: str) -> None: ...
    def get_generation(self, collection_name: str) -> int:
        return 0


# ── Task 1.2: capability method and unsupported response ────────────


def test_abc_default_raises_explicit_unsupported() -> None:
    """A store without native sparse fails honestly, not with empty rows."""
    store = _ThirdPartyStore()
    with pytest.raises(NotImplementedError) as excinfo:
        store.query_native_sparse("documents", "query", 10)
    # The message names the concrete class so operators can attribute it.
    assert "_ThirdPartyStore" in str(excinfo.value)
    assert "native sparse" in str(excinfo.value)


def test_capability_method_contract_shape() -> None:
    """The ABC declares the shared query parameters pinned by the design."""
    signature = inspect.signature(VectorStore.query_native_sparse)
    parameters = signature.parameters
    assert list(parameters) == [
        "self",
        "collection_name",
        "query",
        "n_results",
        "where",
    ]
    assert parameters["where"].default is None
    assert parameters["n_results"].annotation in ("int", int)


def test_native_sparse_score_kind_is_distinct_from_dense() -> None:
    """Sparse and dense canonical score kinds never collide."""
    assert NATIVE_SPARSE_SCORE_KIND == "native_fts_v1"
    assert NATIVE_SPARSE_SCORE_KIND != DENSE_SCORE_KIND


def test_chroma_store_keeps_explicit_unsupported_response() -> None:
    """The quarantined Chroma extra admits it cannot issue native sparse.

    Out of scope by design (ADR-049 quarantine): the contract admits a
    later Chroma implementation, and until then the ABC default's
    honest failure is exactly what this store must produce.
    """
    pytest.importorskip(
        "chromadb", reason="chroma extra not installed; runs in the chroma-extra CI job"
    )
    from omrg.core.vectordb.chroma import ChromaVectorStore

    store = ChromaVectorStore()
    with pytest.raises(NotImplementedError, match="does not support native sparse"):
        store.query_native_sparse("documents", "query", 10)


# ── Tasks 2.1-2.4: LanceDB native FTS adapter ───────────────────────


def _lance_store(tmp_path, name: str = "fts"):
    """Return a LanceVectorStore over an isolated tmp_path database."""
    from omrg.core.vectordb.lancedb import LanceVectorStore

    return LanceVectorStore(uri=str(tmp_path / name))


def _write_rows(store, collection: str, rows: list[tuple[str, str, str]]) -> None:
    """Upsert (id, text, category) rows through the precomputed seam."""
    from omrg.core.vectordb.identity import EmbeddingIdentity

    store.upsert_precomputed(
        collection,
        [row_id for row_id, _text, _category in rows],
        [text for _row_id, text, _category in rows],
        [{"category": category} for _row_id, _text, category in rows],
        [[0.1, 0.2, 0.3, 0.4]] * len(rows),
        embedding_identity=EmbeddingIdentity(provider="test", model="mock"),
    )


_CORPUS = [
    ("history-1", "the colosseum of ancient rome", "history"),
    ("science-1", "quantum computing qubits", "science"),
    ("sport-1", "modern stadium concrete design", "sport"),
]


class TestNativeSparseQueries:
    """Task 2.1: native FTS query execution over the text column."""

    def test_query_ranks_text_matches(self, tmp_path) -> None:
        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        rows = store.query_native_sparse("docs", "colosseum", 5)
        assert [row["id"] for row in rows] == ["history-1"]

    def test_first_use_creates_fts_index_additively(self, tmp_path) -> None:
        """A collection without an index gains one on first native use."""
        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        assert store.native_sparse_coverage("docs") is None
        store.query_native_sparse("docs", "colosseum", 5)
        coverage = store.native_sparse_coverage("docs")
        # Creation indexes pre-existing rows synchronously.
        assert coverage == {"indexed": 3, "unindexed": 0, "total": 3}

    def test_metadata_filter_composes_with_native_query(self, tmp_path) -> None:
        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        _write_rows(store, "docs", [("science-2", "stadium sized quantum array", "science")])
        rows = store.query_native_sparse("docs", "stadium", 5, where={"category": "sport"})
        assert [row["id"] for row in rows] == ["sport-1"]

    def test_absent_collection_reads_empty(self, tmp_path) -> None:
        store = _lance_store(tmp_path)
        assert store.query_native_sparse("absent", "query", 5) == []

    def test_canonical_row_shape(self, tmp_path) -> None:
        """Task 2.3: rows normalise to the shared store-level contract."""
        from omrg.core.vectordb.score import NATIVE_SPARSE_SCORE_KIND

        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        row = store.query_native_sparse("docs", "colosseum", 5)[0]
        assert set(row) == {"id", "document", "metadata", "score", "score_kind"}
        assert row["document"] == "the colosseum of ancient rome"
        assert row["metadata"] == {"category": "history"}
        assert row["score_kind"] == NATIVE_SPARSE_SCORE_KIND
        assert row["score"] > 0.0

    def test_query_does_not_bump_generation(self, tmp_path) -> None:
        """The FTS path never touches the BM25 cache counter (PR #63)."""
        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        before = store.get_generation("docs")
        store.query_native_sparse("docs", "colosseum", 5)
        assert store.get_generation("docs") == before


class TestCollectionsWithoutFTSIndexes:
    """Task 2.2: collections without an FTS index keep working."""

    def test_dense_and_bm25_work_without_index(self, tmp_path) -> None:
        from omrg.core.retrieval.sparse import BM25SparseRetriever

        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        dense = store.query_dense("docs", [0.1, 0.2, 0.3, 0.4], 3)
        assert len(dense) == 3
        ranked = BM25SparseRetriever("docs", store=store).query("colosseum", 1)
        assert ranked[0][1] == "history-1"

    def test_coverage_none_without_index(self, tmp_path) -> None:
        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        assert store.native_sparse_coverage("docs") is None

    def test_coverage_none_for_absent_collection(self, tmp_path) -> None:
        store = _lance_store(tmp_path)
        assert store.native_sparse_coverage("absent") is None


class TestFTSLifecycle:
    """Task 2.4: creation, staleness, refresh, coverage, failure."""

    def test_write_after_index_is_served_after_refresh(self, tmp_path) -> None:
        """Post-index writes surface in the next native query.

        The durable stats show staleness first; the query-triggered
        refresh folds the rows, then the ranking serves them.
        """
        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        store.query_native_sparse("docs", "colosseum", 5)  # creates the index
        _write_rows(store, "docs", [("late-1", "zephyr unique late token", "science")])
        # Durable staleness is observable before the next query...
        coverage = store.native_sparse_coverage("docs")
        assert coverage == {"indexed": 3, "unindexed": 1, "total": 4}
        # ...and the next native query refreshes and serves the new row.
        rows = store.query_native_sparse("docs", "zephyr", 5)
        assert [row["id"] for row in rows] == ["late-1"]
        assert store.native_sparse_coverage("docs") == {
            "indexed": 4,
            "unindexed": 0,
            "total": 4,
        }

    def test_delete_after_index_excludes_rows(self, tmp_path) -> None:
        """Deleted rows never return from the native path."""
        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        store.query_native_sparse("docs", "colosseum", 5)
        store.delete_where("docs", {"category": "history"})
        assert store.query_native_sparse("docs", "colosseum", 5) == []

    def test_replacement_refreshes_indexed_content(self, tmp_path) -> None:
        """Upserting an existing id replaces its indexed text."""
        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        store.query_native_sparse("docs", "colosseum", 5)
        _write_rows(store, "docs", [("history-1", "replaced theta content", "history")])
        rows = store.query_native_sparse("docs", "theta", 5)
        assert [row["id"] for row in rows] == ["history-1"]
        assert rows[0]["document"] == "replaced theta content"
        # The old text no longer matches the replaced row.
        assert store.query_native_sparse("docs", "colosseum", 5) == []

    def test_query_failure_propagates_for_retrieval_fallback(self, tmp_path, monkeypatch) -> None:
        """Engine failures raise so the retrieval layer can fall back."""
        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        store.query_native_sparse("docs", "colosseum", 5)  # ensure index exists

        def _boom(*_args, **_kwargs):
            raise RuntimeError("engine exploded")

        table = store._open_table("docs")
        monkeypatch.setattr(type(table), "search", _boom)
        with pytest.raises(RuntimeError, match="engine exploded"):
            store.query_native_sparse("docs", "colosseum", 5)

    def test_index_creation_failure_propagates_for_fallback(self, tmp_path, monkeypatch) -> None:
        """First-use creation failure raises (the BM25 fallback signal)."""
        from omrg.core.vectordb import lance_fts

        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)

        def _boom(_table):
            raise RuntimeError("cannot create index")

        monkeypatch.setattr(lance_fts, "ensure_fts_index", _boom)
        with pytest.raises(RuntimeError, match="cannot create index"):
            store.query_native_sparse("docs", "colosseum", 5)

    def test_refresh_failure_propagates_for_fallback(self, tmp_path, monkeypatch) -> None:
        """Refresh failure on a stale index raises (lifecycle fallback)."""
        from omrg.core.vectordb import lance_fts

        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        store.query_native_sparse("docs", "colosseum", 5)  # creates the index
        _write_rows(store, "docs", [("late-1", "zephyr late token", "science")])

        def _boom(_table):
            raise RuntimeError("optimize failed")

        monkeypatch.setattr(lance_fts, "refresh_fts_index", _boom)
        with pytest.raises(RuntimeError, match="optimize failed"):
            store.query_native_sparse("docs", "zephyr", 5)


class TestNativeFTSProbe:
    """The real capability probe used by composition (task 3.2 input)."""

    def test_probe_true_on_locked_runtime(self) -> None:
        from omrg.core.vectordb.lance_fts import probe_native_fts

        assert probe_native_fts() is True

    def test_probe_false_when_fts_surface_missing(self, monkeypatch) -> None:
        """A runtime without the FTS surface probes as unavailable."""
        import sys

        from omrg.core.vectordb.lance_fts import probe_native_fts

        # A None module entry makes `from lancedb.index import FTS`
        # raise ImportError inside the probe, which must report False.
        monkeypatch.setitem(sys.modules, "lancedb.index", None)
        assert probe_native_fts() is False


# ── Pipeline integration: hybrid search through the native backend ──


def _native_settings(effective_settings, backend: str = "native"):
    """Hybrid-enabled settings with an explicit sparse backend."""
    return effective_settings(
        hybrid_enabled=True,
        hybrid_sparse_backend=backend,
        rerank_enabled=False,
        similarity_threshold=0.0,
    )


class TestHybridNativePipeline:
    """Spec scenarios for native execution through ``pipeline.search``."""

    @staticmethod
    def _patch_dense_query(monkeypatch, dim: int = 4) -> None:
        import omrg.core.retrieval.dense as dense

        # Unit-norm so the (default-on) embedding norm guard admits it.
        value = [1.0 / (dim**0.5)] * dim
        monkeypatch.setattr(dense, "_embed_query", lambda _q, _em=None, _c=None: value)

    def test_native_selected_and_supported_executes_native(
        self, tmp_path, monkeypatch, effective_settings
    ) -> None:
        """Real native execution: FTS ranking feeds the hybrid fusion."""
        import omrg.core.retrieval.pipeline as retrieval
        from omrg.core.retrieval.sparse_dispatch import reset_warning_state

        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        self._patch_dense_query(monkeypatch)
        reset_warning_state()
        results = retrieval.search(
            "colosseum",
            top_k=2,
            rerank=False,
            hybrid=True,
            store=store,
            collection_name="docs",
            effective_settings=_native_settings(effective_settings),
            include_diagnostics=True,
        )
        # The colosseum row is found via the native FTS ranking (dense
        # vectors are all near-identical, so only sparse evidence can
        # discriminate), and the diagnostics report the native backend.
        assert any(row["source"] for row in results)
        assert all(row.get("sparse_backend") == "native" for row in results)

    def test_native_runtime_failure_falls_back_with_warning(
        self, tmp_path, monkeypatch, caplog, effective_settings
    ) -> None:
        """A native runtime failure warns once and serves BM25 results."""
        import logging

        import omrg.core.retrieval.pipeline as retrieval
        from omrg.core.retrieval import sparse_dispatch
        from omrg.core.retrieval.sparse_dispatch import reset_warning_state

        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        self._patch_dense_query(monkeypatch)

        real_query_rows = sparse_dispatch._sparse_query_rows

        def _boom_only_native(*args, **kwargs):
            if kwargs.get("backend", args[4] if len(args) > 4 else "bm25") == "native":
                raise RuntimeError("native exploded")
            return real_query_rows(*args, **kwargs)

        monkeypatch.setattr(sparse_dispatch, "_sparse_query_rows", _boom_only_native)
        reset_warning_state()
        with caplog.at_level(logging.WARNING):
            results = retrieval.search(
                "colosseum",
                top_k=2,
                rerank=False,
                hybrid=True,
                store=store,
                collection_name="docs",
                effective_settings=_native_settings(effective_settings),
                include_diagnostics=True,
            )
        assert any(
            "Falling back to the BM25 sparse retriever" in record.message
            for record in caplog.records
        )
        # The sparse ranking is NOT labelled native after the fallback.
        assert all(row.get("sparse_backend") == "bm25" for row in results)

    def test_mixed_fts_coverage_warns_once_per_collection(
        self, tmp_path, monkeypatch, caplog, effective_settings
    ) -> None:
        """Partial FTS coverage triggers the one-shot restated warning."""
        import logging

        import omrg.core.retrieval.pipeline as retrieval
        from omrg.core.retrieval.sparse_dispatch import reset_warning_state

        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        # Create the index, then leave a durable unindexed row.
        store.query_native_sparse("docs", "colosseum", 5)
        _write_rows(store, "docs", [("late-1", "zephyr late token", "science")])
        self._patch_dense_query(monkeypatch)
        reset_warning_state()

        def _no_refresh(_table):  # keep the stale marker durable
            pass

        from omrg.core.vectordb import lance_fts

        monkeypatch.setattr(lance_fts, "refresh_fts_index", _no_refresh)
        with caplog.at_level(logging.WARNING):
            retrieval.search(
                "colosseum",
                top_k=2,
                rerank=False,
                hybrid=True,
                store=store,
                collection_name="docs",
                effective_settings=_native_settings(effective_settings),
            )
        coverage_warnings = [r for r in caplog.records if "mixed full-text coverage" in r.message]
        assert len(coverage_warnings) == 1
        assert "docs" in coverage_warnings[0].message

    def test_bm25_path_skips_fts_coverage_warning(
        self, tmp_path, monkeypatch, caplog, effective_settings
    ) -> None:
        """The BM25 path never emits the FTS mixed-coverage warning."""
        import logging

        import omrg.core.retrieval.pipeline as retrieval
        from omrg.core.retrieval.sparse_dispatch import reset_warning_state

        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        store.query_native_sparse("docs", "colosseum", 5)
        _write_rows(store, "docs", [("late-1", "zephyr late token", "science")])
        self._patch_dense_query(monkeypatch)
        reset_warning_state()
        with caplog.at_level(logging.WARNING):
            retrieval.search(
                "colosseum",
                top_k=2,
                rerank=False,
                hybrid=True,
                store=store,
                collection_name="docs",
                effective_settings=_native_settings(effective_settings, backend="bm25"),
            )
        assert not [r for r in caplog.records if "mixed full-text coverage" in r.message]

    def test_metadata_filter_reaches_native_ranking(
        self, tmp_path, monkeypatch, effective_settings
    ) -> None:
        """Hybrid metadata filters constrain the native sparse ranking."""
        import omrg.core.retrieval.pipeline as retrieval
        from omrg.core.retrieval.sparse_dispatch import reset_warning_state

        store = _lance_store(tmp_path)
        _write_rows(store, "docs", _CORPUS)
        _write_rows(store, "docs", [("science-2", "stadium sized quantum array", "science")])
        self._patch_dense_query(monkeypatch)
        reset_warning_state()
        results = retrieval.search(
            "stadium",
            top_k=2,
            rerank=False,
            hybrid=True,
            metadata_filter={"category": "sport"},
            store=store,
            collection_name="docs",
            effective_settings=_native_settings(effective_settings),
        )
        assert results
        assert all(row["metadata"].get("category") == "sport" for row in results)


# ── Dispatch-seam coverage: warning state, legacy scan, registry errors ──


class _FakeCoverageStore:
    """Minimal store exposing only the FTS coverage signal."""

    def __init__(self, stats: dict | None) -> None:
        self._stats = stats
        self.calls = 0

    def native_sparse_coverage(self, collection_name: str) -> dict | None:
        self.calls += 1
        if isinstance(self._stats, Exception):
            raise self._stats
        return self._stats


class _FakeLegacyStore:
    """Sparse-vector-era store: no coverage method, paged metadata scan."""

    def __init__(self, metadatas: list[dict | None] | Exception) -> None:
        self._metadatas = metadatas

    def iter_metadatas(self, collection_name: str, page_size=None):
        if isinstance(self._metadatas, Exception):
            raise self._metadatas
        yield from self._metadatas


class TestMixedCoverageWarningState:
    """The one-shot warning state machine in sparse_dispatch."""

    def test_fts_partial_coverage_warns_once(self, caplog) -> None:
        import logging

        from omrg.core.retrieval.sparse_dispatch import (
            _emit_mixed_coverage_warning,
            reset_warning_state,
        )

        reset_warning_state()
        store = _FakeCoverageStore({"indexed": 2, "unindexed": 1, "total": 3})
        with caplog.at_level(logging.WARNING):
            _emit_mixed_coverage_warning("cov", store)  # type: ignore[arg-type]
            _emit_mixed_coverage_warning("cov", store)  # type: ignore[arg-type]
        warnings_seen = [r for r in caplog.records if "mixed full-text coverage" in r.message]
        assert len(warnings_seen) == 1

    def test_fts_full_or_absent_coverage_stays_silent(self, caplog) -> None:
        import logging

        from omrg.core.retrieval.sparse_dispatch import (
            _emit_mixed_coverage_warning,
            reset_warning_state,
        )

        reset_warning_state()
        with caplog.at_level(logging.WARNING):
            _emit_mixed_coverage_warning(
                "full", _FakeCoverageStore({"indexed": 3, "unindexed": 0, "total": 3})
            )  # type: ignore[arg-type]
            _emit_mixed_coverage_warning("absent", _FakeCoverageStore(None))  # type: ignore[arg-type]
        assert not [r for r in caplog.records if "mixed" in r.message]

    def test_coverage_probe_failure_stays_silent(self, caplog) -> None:
        import logging

        from omrg.core.retrieval.sparse_dispatch import (
            _emit_mixed_coverage_warning,
            reset_warning_state,
        )

        reset_warning_state()
        with caplog.at_level(logging.WARNING):
            _emit_mixed_coverage_warning("boom", _FakeCoverageStore(RuntimeError("x")))  # type: ignore[arg-type]
        assert not caplog.records

    def test_legacy_paged_scan_warns_once(self, caplog) -> None:
        """Stores without the coverage signal keep the Chroma-era scan."""
        import logging

        from omrg.core.retrieval.sparse_dispatch import (
            _emit_mixed_coverage_warning,
            reset_warning_state,
        )

        reset_warning_state()
        store = _FakeLegacyStore([{"has_sparse_vector": True}, {"has_sparse_vector": True}, {}])
        with caplog.at_level(logging.WARNING):
            _emit_mixed_coverage_warning("legacy", store)  # type: ignore[arg-type]
            _emit_mixed_coverage_warning("legacy", store)  # type: ignore[arg-type]
        legacy_warnings = [r for r in caplog.records if "sparse vectors" in r.message]
        assert len(legacy_warnings) == 1
        assert "2/3" in legacy_warnings[0].message

    def test_legacy_scan_failure_stays_silent(self, caplog) -> None:
        import logging

        from omrg.core.retrieval.sparse_dispatch import (
            _emit_mixed_coverage_warning,
            reset_warning_state,
        )

        reset_warning_state()
        with caplog.at_level(logging.WARNING):
            _emit_mixed_coverage_warning("scan-boom", _FakeLegacyStore(RuntimeError("scan died")))  # type: ignore[arg-type]
        assert not [r for r in caplog.records if "sparse" in r.message]


class TestSparseRegistryErrors:
    """The registry's failure modes list names and preserve causes."""

    def test_unknown_name_lists_available(self) -> None:
        import pytest as _pytest

        from omrg.core.retrieval import sparse_registry

        with _pytest.raises(KeyError, match="Available"):
            sparse_registry.get("tantivy")

    def test_broken_import_string_raises_import_error(self) -> None:
        import pytest as _pytest

        from omrg.core.retrieval import sparse_registry

        sparse_registry.register("__broken__", "rag_mpp.nonexistent_module:Thing")
        try:
            with _pytest.raises(ImportError, match="could not be imported"):
                sparse_registry.get("__broken__")
        finally:
            sparse_registry._registry.pop("__broken__", None)
            sparse_registry._cache.pop("__broken__", None)


class TestNativeRetrieverEdges:
    """Edge branches of the retrieval-level native backend."""

    def test_zero_top_n_returns_empty(self, tmp_path) -> None:
        from omrg.core.retrieval.native_sparse import NativeSparseRetriever

        store = _lance_store(tmp_path)
        assert NativeSparseRetriever("docs", store=store).query("anything", 0) == []

    def test_default_store_resolution(self) -> None:
        from omrg.core.retrieval.native_sparse import NativeSparseRetriever
        from omrg.core.vectordb import get_default_store

        retriever = NativeSparseRetriever("documents")
        assert retriever._get_store() is get_default_store()

    def test_identity_conflict_rejects_before_fts_mutation(self, tmp_path) -> None:
        """A conflicting EmbeddingIdentity cannot query OR index the collection.

        Mirrors the dense-path guard order: the identity check runs
        after the absent-table check and before any lifecycle work, so
        a mismatched store cannot create an FTS index on a collection
        it does not own.
        """
        from omrg.core.vectordb.identity import EmbeddingIdentity
        from omrg.core.vectordb.lancedb import LanceVectorStore

        uri = str(tmp_path / "identity-guard")
        writer = LanceVectorStore(
            uri=uri, embedding_identity=EmbeddingIdentity(provider="p1", model="m1")
        )
        writer.upsert_precomputed(
            "docs",
            ["a"],
            ["zephyr identity probe"],
            [{"category": "science"}],
            [[0.5, 0.5, 0.5, 0.5]],
            embedding_identity=EmbeddingIdentity(provider="p1", model="m1"),
        )

        intruder = LanceVectorStore(
            uri=uri, embedding_identity=EmbeddingIdentity(provider="p2", model="m2")
        )
        with pytest.raises(ValueError, match="(?i)identity|mismatch|embedding"):
            intruder.query_native_sparse("docs", "zephyr", 5)
        # No FTS index was created by the rejected query.
        assert intruder.native_sparse_coverage("docs") is None
