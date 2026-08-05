"""Tests for the OpenSpec ``rag-hybrid-retrieval`` change.

These tests intentionally pin the public contracts introduced by the
hybrid retrieval spec: opt-in API surface, RRF math, BM25 fallback
behaviour, cache invalidation, and reranker integration.
"""

from __future__ import annotations

import logging
import inspect
from unittest.mock import MagicMock

import pytest


class FakeCollection:
    """Minimal ChromaDB collection test double."""

    def __init__(self, name: str, rows: list[dict]) -> None:
        self.name = name
        self.rows = rows
        self.get_calls = 0

    def count(self) -> int:
        return len(self.rows)

    def get(self, *args, **kwargs) -> dict:
        self.get_calls += 1
        limit = kwargs.get("limit")
        offset = kwargs.get("offset", 0)
        rows = self.rows[offset: offset + limit] if limit is not None else self.rows
        return {
            "ids": [row["id"] for row in rows],
            "documents": [row["text"] for row in rows],
            "metadatas": [row.get("metadata", {}) for row in rows],
        }

    def query(self, **kwargs) -> dict:
        n_results = kwargs.get("n_results", len(self.rows))
        rows = self.rows[:n_results]
        return {
            "ids": [[row["id"] for row in rows]],
            "documents": [[row["text"] for row in rows]],
            "metadatas": [[row.get("metadata", {}) for row in rows]],
            "distances": [[row.get("distance", float(i + 1)) for i, row in enumerate(rows)]],
        }


class FakePersistentClient:
    """Chroma PersistentClient test double keyed by collection name."""

    def __init__(self, collections: dict[str, FakeCollection]) -> None:
        self.collections = collections

    def get_collection(self, name: str) -> FakeCollection:
        if name not in self.collections:
            raise ValueError(f"missing collection: {name}")
        return self.collections[name]

    def get_or_create_collection(self, name: str) -> FakeCollection:
        if name not in self.collections:
            self.collections[name] = FakeCollection(name, [])
        return self.collections[name]

    def list_collections(self):
        return list(self.collections.values())

    def delete_collection(self, name: str) -> None:
        self.collections.pop(name, None)


class FakeStore:
    """Minimal VectorStore test double wrapping a FakeCollection.

    Implements just the methods ``BM25SparseRetriever`` calls: ``count``,
    ``iter_documents``, ``get_generation``, and ``bump_generation``.
    Delegates paging to ``FakeCollection.get`` so ``get_calls`` is
    incremented exactly as the real store would.
    """

    def __init__(self, collection: FakeCollection) -> None:
        self._collection = collection
        self._generations: dict[str, int] = {}

    def count(self, name: str) -> int:
        return self._collection.count()

    def iter_documents(self, name: str, page_size: int | None = None):
        page_size = page_size or 10000
        offset = 0
        while True:
            batch = self._collection.get(
                include=["documents", "metadatas"],
                limit=page_size,
                offset=offset,
            )
            ids = batch.get("ids") or []
            docs = batch.get("documents") or []
            metas = batch.get("metadatas") or []
            if not ids:
                break
            for idx, doc_id in enumerate(ids):
                metadata = (
                    metas[idx]
                    if idx < len(metas) and isinstance(metas[idx], dict)
                    else {}
                )
                text = docs[idx] if idx < len(docs) else ""
                yield (str(doc_id), str(text), dict(metadata))
            if len(ids) < page_size:
                break
            offset += len(ids)

    def get_generation(self, name: str) -> int:
        return self._generations.get(name, 0)

    def bump_generation(self, name: str) -> None:
        self._generations[name] = self._generations.get(name, 0) + 1


def test_search_signature_exposes_hybrid_opt_in() -> None:
    """``retrieval.search`` must expose an opt-in ``hybrid`` parameter.

    The default is ``None`` — the effective value resolves from
    ``settings.retrieval.hybrid_enabled`` at call time (ADR-031), so a post-import
    settings patch is honoured.
    """
    from rag_mcp.core.retrieval import search

    param = inspect.signature(search).parameters.get("hybrid")

    assert param is not None
    assert param.default is None


def test_mcp_search_documents_signature_exposes_hybrid_opt_in() -> None:
    """The MCP tool must expose the same opt-in ``hybrid`` parameter."""
    from rag_mcp.transports.mcp import search_documents

    param = inspect.signature(search_documents).parameters.get("hybrid")

    assert param is not None
    assert param.default is None



async def test_mcp_search_documents_passes_hybrid_through(monkeypatch) -> None:
    """MCP calls must forward ``hybrid`` unchanged to retrieval.search."""
    import rag_mcp.transports.mcp as server

    mock_search = MagicMock(return_value=[])
    monkeypatch.setattr(server, "search", mock_search)

    await server.search_documents("needle", hybrid=True, rerank=False)

    mock_search.assert_called_once()
    assert mock_search.call_args.kwargs["hybrid"] is True


def test_hybrid_config_defaults() -> None:
    """OpenSpec defaults are stable and safe for v1 rollout."""
    import rag_mcp.config as config

    assert config.HYBRID_ENABLED is False
    assert config.HYBRID_RRF_K == 60
    assert config.HYBRID_SPARSE_BACKEND == "bm25"


def test_rrf_worked_example_from_spec() -> None:
    """A chunk ranked 3rd and 5th scores ``1/(60+3)+1/(60+5)``."""
    from rag_mcp.core.retrieval import reciprocal_rank_fusion

    scores = reciprocal_rank_fusion(
        [["d1", "d2", "target"], ["a", "b", "c", "d", "target"]],
        k=60,
    )

    assert scores["target"] == pytest.approx(1 / (60 + 3) + 1 / (60 + 5))


def test_rrf_chunk_present_in_only_one_ranking() -> None:
    """Missing sparse/dense ranks contribute no term to the RRF score."""
    from rag_mcp.core.retrieval import reciprocal_rank_fusion

    scores = reciprocal_rank_fusion([["dense_only"], ["other"]], k=60)

    assert scores["dense_only"] == pytest.approx(1 / 61)
    assert scores["other"] == pytest.approx(1 / 61)


def test_rrf_with_metadata_empty_sparse_ranking_keeps_dense_order() -> None:
    """Empty sparse rankings must not error or disturb dense-only order."""
    from rag_mcp.core.retrieval import rrf_with_metadata

    dense = [
        {"id": "a", "text": "alpha", "metadata": {"source": "a.txt"}},
        {"id": "b", "text": "beta", "metadata": {"source": "b.txt"}},
    ]

    fused = rrf_with_metadata(dense_ranked=dense, sparse_ranked=[], k=60)

    assert [row["id"] for row in fused] == ["a", "b"]
    assert all("fused_score" in row for row in fused)


def test_default_english_tokenizer_lowercases_splits_and_removes_stopwords() -> None:
    """BM25 tokenisation should be deterministic and useful for rare terms."""
    from rag_mcp.core.retrieval.sparse import tokenize_english

    tokens = tokenize_english("The Colosseum identifier ZXQ-77 appears in Rome.")

    assert "the" not in tokens
    assert "in" not in tokens
    assert "colosseum" in tokens
    assert "zxq" in tokens
    assert "77" in tokens
    assert all(token == token.lower() for token in tokens)


def test_bm25_sparse_retriever_empty_collection_returns_empty() -> None:
    """The BM25 fallback must gracefully handle empty collections."""
    from rag_mcp.core.retrieval.sparse import BM25SparseRetriever

    collection = FakeCollection("empty", [])
    store = FakeStore(collection)
    retriever = BM25SparseRetriever(collection_name="empty", store=store)

    assert retriever.query("anything", top_n=5) == []


def test_bm25_sparse_retriever_ranks_exact_rare_term_first() -> None:
    """Rare exact-match identifiers should be promoted by BM25."""
    from rag_mcp.core.retrieval.sparse import BM25SparseRetriever

    collection = FakeCollection(
        "rare_terms",
        [
            {"id": "semantic", "text": "Ancient amphitheatres hosted spectacles.", "metadata": {"file_path": "semantic.txt"}},
            {"id": "rare", "text": "The continuity note contains ZXQ-77 for the Colosseum.", "metadata": {"file_path": "rare.txt"}},
            {"id": "noise", "text": "Modern stadium design uses concrete.", "metadata": {"file_path": "noise.txt"}},
        ],
    )
    store = FakeStore(collection)
    retriever = BM25SparseRetriever(collection_name="rare_terms", store=store)

    results = retriever.query("ZXQ-77", top_n=3)

    assert results
    rank, doc_id, text, metadata = results[0]
    assert rank == 1
    assert doc_id == "rare"
    assert "ZXQ-77" in text
    assert metadata["file_path"] == "rare.txt"


def test_bm25_reuses_cached_index_when_generation_is_unchanged(monkeypatch) -> None:
    """Two consecutive queries without writes should scan the store only once."""
    from rag_mcp.core.retrieval.sparse import BM25SparseRetriever

    collection = FakeCollection(
        "cache_reuse",
        [{"id": "a", "text": "alpha rareterm", "metadata": {}}],
    )
    store = FakeStore(collection)
    store._generations["cache_reuse"] = 0
    retriever = BM25SparseRetriever(collection_name="cache_reuse", store=store)

    retriever.query("rareterm", top_n=1)
    retriever.query("rareterm", top_n=1)

    assert collection.get_calls == 1


def test_bm25_rebuilds_when_generation_advances(monkeypatch) -> None:
    """A generation bump from ingest/delete must invalidate the BM25 cache."""
    from rag_mcp.core.retrieval.sparse import BM25SparseRetriever

    collection = FakeCollection(
        "cache_rebuild",
        [{"id": "old", "text": "old token", "metadata": {}}],
    )
    store = FakeStore(collection)
    store._generations["cache_rebuild"] = 0
    retriever = BM25SparseRetriever(collection_name="cache_rebuild", store=store)

    assert retriever.query("newtoken", top_n=5) == []

    collection.rows.append({"id": "new", "text": "newtoken appears", "metadata": {}})
    store.bump_generation("cache_rebuild")

    rebuilt = retriever.query("newtoken", top_n=5)

    assert collection.get_calls == 2
    assert [row[1] for row in rebuilt] == ["new"]


def test_remove_document_generation_rebuild_excludes_deleted_chunk() -> None:
    """Deleting between sparse queries bumps generation and rebuilds cache."""
    from rag_mcp.core.retrieval.sparse import BM25SparseRetriever

    collection = FakeCollection(
        "delete_rebuild",
        [{"id": "gone", "text": "raredelete token", "metadata": {}}],
    )
    store = FakeStore(collection)
    store._generations["delete_rebuild"] = 0
    retriever = BM25SparseRetriever("delete_rebuild", store=store)

    assert [row[1] for row in retriever.query("raredelete", top_n=5)] == ["gone"]
    collection.rows.clear()
    store.bump_generation("delete_rebuild")

    assert retriever.query("raredelete", top_n=5) == []
    assert BM25SparseRetriever._cache["delete_rebuild"].generation == 1


def test_remove_collection_generation_invalidates_cache() -> None:
    """Collection removal generation bump invalidates the cached BM25 index."""
    from rag_mcp.core.retrieval.sparse import BM25SparseRetriever

    collection = FakeCollection(
        "drop_rebuild",
        [{"id": "old", "text": "dropme token", "metadata": {}}],
    )
    store = FakeStore(collection)
    store._generations["drop_rebuild"] = 0
    retriever = BM25SparseRetriever("drop_rebuild", store=store)

    retriever.query("dropme", top_n=5)
    collection.rows[:] = [{"id": "new", "text": "replacement token", "metadata": {}}]
    store.bump_generation("drop_rebuild")

    assert [row[1] for row in retriever.query("replacement", top_n=5)] == ["new"]


def test_hybrid_false_matches_dense_only_result_shape(monkeypatch) -> None:
    """The dense-only default must remain byte-for-byte compatible."""
    import chromadb
    import rag_mcp.core.retrieval.pipeline as retrieval
    import rag_mcp.core.retrieval.dense as _dense

    collection = FakeCollection(
        "documents",
        [{"id": "dense", "text": "dense text", "metadata": {"file_path": "dense.txt"}, "distance": 1.0}],
    )
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: FakePersistentClient({"documents": collection}))
    monkeypatch.setattr(_dense, "_embed_query", lambda query: [0.0] * 384)

    implicit = retrieval.search("query", top_k=1, rerank=False)
    explicit = retrieval.search("query", top_k=1, rerank=False, hybrid=False)

    assert explicit == implicit


def test_hybrid_rerank_receives_fused_sparse_candidate(monkeypatch) -> None:
    """Hybrid + rerank must feed the reranker the fused dense+sparse pool."""
    import chromadb
    import rag_mcp.config as config
    import rag_mcp.core.retrieval.pipeline as retrieval
    import rag_mcp.core.retrieval.dense as _dense


    dense_rows = [
        {"id": "dense", "text": "semantic amphitheatre", "metadata": {"file_path": "dense.txt"}, "distance": 0.1},
        {"id": "sparse", "text": "ZXQ-77 exact identifier", "metadata": {"file_path": "sparse.txt"}, "distance": 9.0},
    ]
    collection = FakeCollection("documents", dense_rows)
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: FakePersistentClient({"documents": collection}))
    monkeypatch.setattr(_dense, "_embed_query", lambda query: [0.0] * 384)
    from rag_mcp.core.settings import EffectiveSettings, RetrievalBlock, set_default_effective_settings

    set_default_effective_settings(EffectiveSettings(retrieval=RetrievalBlock(rerank_max_fetch=2, rerank_fetch_multiplier=2)))

    captured: dict[str, list[dict]] = {}

    class CapturingReranker:
        def rerank(self, query: str, results: list[dict], top_k: int) -> list[dict]:
            captured["results"] = [dict(row) for row in results]
            for row in results:
                row["_reranked"] = True
            return results[:top_k]

    # Inject the capturing reranker directly via the DI parameter.
    retrieval.search("ZXQ-77", top_k=1, rerank=True, hybrid=True, reranker=CapturingReranker())

    assert "results" in captured
    assert any(row["source"] == "sparse.txt" for row in captured["results"])
    assert len(captured["results"]) == 2


def test_hybrid_public_shape_strips_rank_diagnostics(monkeypatch) -> None:
    """MCP/CLI public result shape should not leak internal fusion fields."""
    import chromadb
    import rag_mcp.config as config
    import rag_mcp.core.retrieval.pipeline as retrieval
    import rag_mcp.core.retrieval.dense as _dense

    collection = FakeCollection(
        "documents",
        [
            {"id": "dense", "text": "semantic amphitheatre", "metadata": {"file_path": "dense.txt"}, "distance": 0.1},
            {"id": "sparse", "text": "Colosseum exact identifier", "metadata": {"file_path": "sparse.txt"}, "distance": 9.0},
        ],
    )
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: FakePersistentClient({"documents": collection}))
    monkeypatch.setattr(_dense, "_embed_query", lambda query: [0.0] * 384)
    from rag_mcp.core.settings import EffectiveSettings, RetrievalBlock, set_default_effective_settings

    set_default_effective_settings(EffectiveSettings(retrieval=RetrievalBlock(rerank_max_fetch=2, rerank_fetch_multiplier=2)))

    public_results = retrieval.search("Colosseum", top_k=2, rerank=False, hybrid=True)

    assert public_results
    for result in public_results:
        assert "id" not in result
        assert "fused_score" not in result
        assert "dense_rank" not in result
        assert "sparse_rank" not in result
        assert "fused_rank" not in result


def test_hybrid_diagnostics_are_available_for_experiments(monkeypatch) -> None:
    """Experiment 9 can opt into fusion rank diagnostics explicitly."""
    import chromadb
    import rag_mcp.config as config
    import rag_mcp.core.retrieval.pipeline as retrieval
    import rag_mcp.core.retrieval.dense as _dense

    collection = FakeCollection(
        "documents",
        [{"id": "target", "text": "Colosseum exact identifier", "metadata": {"file_path": "target.txt"}, "distance": 5.0}],
    )
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: FakePersistentClient({"documents": collection}))
    monkeypatch.setattr(_dense, "_embed_query", lambda query: [0.0] * 384)
    from rag_mcp.core.settings import EffectiveSettings, RetrievalBlock, set_default_effective_settings

    set_default_effective_settings(EffectiveSettings(retrieval=RetrievalBlock(rerank_max_fetch=1, rerank_fetch_multiplier=1)))

    results = retrieval.search(
        "Colosseum",
        top_k=1,
        rerank=False,
        hybrid=True,
        include_diagnostics=True,
    )

    assert results[0]["id"] == "target"
    assert "sparse_rank" in results[0]
    assert results[0]["fused_rank"] == 1


def test_native_mixed_coverage_warning_is_one_shot(monkeypatch, caplog) -> None:
    """Native sparse mixed coverage should warn once with remediation text."""
    import chromadb
    import rag_mcp.config as config
    import rag_mcp.core.retrieval.pipeline as retrieval
    import rag_mcp.core.retrieval.dense as _dense

    collection = FakeCollection(
        "mixed_native",
        [
            {"id": "with_sparse", "text": "has sparse", "metadata": {"file_path": "a.txt", "has_sparse_vector": True}},
            {"id": "without_sparse", "text": "missing sparse", "metadata": {"file_path": "b.txt"}},
        ],
    )
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: FakePersistentClient({"mixed_native": collection}))
    monkeypatch.setattr(_dense, "_embed_query", lambda query: [0.0] * 384)
    from rag_mcp.core.settings import EffectiveSettings, RetrievalBlock, set_default_effective_settings

    set_default_effective_settings(EffectiveSettings(retrieval=RetrievalBlock(hybrid_sparse_backend="native")))
    monkeypatch.setattr(retrieval, "_selected_sparse_backend", lambda _s: "native")
    if hasattr(retrieval, "_warned_collections"):
        retrieval._warned_collections.clear()
    if hasattr(retrieval, "_warned_native_fallback_collections"):
        retrieval._warned_native_fallback_collections.clear()

    with caplog.at_level(logging.WARNING):
        retrieval.search("query", collection_name="mixed_native", rerank=False, hybrid=True)
        retrieval.search("query", collection_name="mixed_native", rerank=False, hybrid=True)

    warnings = [
        r.message
        for r in caplog.records
        if "mixed_native" in r.message and "mixed coverage" in r.message
    ]
    assert len(warnings) == 1
    assert "re-ingest" in warnings[0].lower() or "reingest" in warnings[0].lower()


def test_mixed_coverage_warning_uses_paged_metadata_scan(monkeypatch, caplog) -> None:
    """Native coverage checks must respect CHROMA_SCAN_PAGE_SIZE paging."""
    import chromadb
    import rag_mcp.config as config
    import rag_mcp.core.retrieval.pipeline as retrieval
    import rag_mcp.core.retrieval.dense as _dense

    rows = [
        {"id": "with_sparse", "text": "has sparse", "metadata": {"file_path": "a.txt", "has_sparse_vector": True}},
        {"id": "without_sparse", "text": "missing sparse", "metadata": {"file_path": "b.txt"}},
        {"id": "without_sparse_2", "text": "missing sparse again", "metadata": {"file_path": "c.txt"}},
    ]
    collection = FakeCollection("paged_native", rows)
    # Page size is read from the composition-root default, not the config
    # singleton, now that core no longer imports config.
    from rag_mcp.core.settings import (
        EffectiveSettings,
        set_default_effective_settings,
    )

    set_default_effective_settings(EffectiveSettings(chroma_scan_page_size=1))
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: FakePersistentClient({"paged_native": collection}))
    monkeypatch.setattr(_dense, "_embed_query", lambda query: [0.0] * 384)
    monkeypatch.setattr(retrieval, "_selected_sparse_backend", lambda _s: "native")
    retrieval._warned_collections.clear()
    retrieval._warned_native_fallback_collections.clear()

    with caplog.at_level(logging.WARNING):
        retrieval.search("query", collection_name="paged_native", rerank=False, hybrid=True)

    assert collection.get_calls >= 3
    assert any("1/3 chunks" in record.message for record in caplog.records)


def test_native_sparse_placeholder_falls_back_to_bm25_not_dense_only(monkeypatch, caplog) -> None:
    """Selected native without real query support must use BM25 sparse results."""
    import chromadb
    import rag_mcp.config as config
    import rag_mcp.core.retrieval.pipeline as retrieval
    import rag_mcp.core.retrieval.dense as _dense

    collection = FakeCollection(
        "native_fallback",
        [
            {"id": "dense", "text": "generic amphitheatre", "metadata": {"file_path": "dense.txt"}, "distance": 0.1},
            {"id": "bm25", "text": "Colosseum exact rare term", "metadata": {"file_path": "bm25.txt"}, "distance": 9.0},
        ],
    )
    from rag_mcp.core.settings import EffectiveSettings, RetrievalBlock, set_default_effective_settings

    set_default_effective_settings(EffectiveSettings(retrieval=RetrievalBlock(rerank_max_fetch=2, rerank_fetch_multiplier=2)))
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: FakePersistentClient({"native_fallback": collection}))
    monkeypatch.setattr(_dense, "_embed_query", lambda query: [0.0] * 384)
    monkeypatch.setattr(retrieval, "_selected_sparse_backend", lambda _s: "native")
    retrieval._warned_native_fallback_collections.clear()

    with caplog.at_level(logging.WARNING):
        results = retrieval.search(
            "Colosseum",
            collection_name="native_fallback",
            top_k=2,
            rerank=False,
            hybrid=True,
            include_diagnostics=True,
        )

    assert any(row["source"] == "bm25.txt" and row["sparse_rank"] == 1 for row in results)
    assert any("Falling back to the BM25 sparse retriever" in record.message for record in caplog.records)


def test_bm25_path_suppresses_mixed_coverage_warning(monkeypatch, caplog) -> None:
    """BM25 indexes all chunks it sees and must not warn about sparse coverage."""
    import chromadb
    import rag_mcp.core.retrieval.pipeline as retrieval
    import rag_mcp.core.retrieval.dense as _dense

    collection = FakeCollection(
        "bm25_no_warn",
        [
            {"id": "a", "text": "rare token", "metadata": {"file_path": "a.txt"}},
            {"id": "b", "text": "other token", "metadata": {"file_path": "b.txt", "has_sparse_vector": True}},
        ],
    )
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: FakePersistentClient({"bm25_no_warn": collection}))
    monkeypatch.setattr(_dense, "_embed_query", lambda query: [0.0] * 384)
    monkeypatch.setattr(retrieval, "_selected_sparse_backend", lambda _s: "bm25")

    with caplog.at_level(logging.WARNING):
        retrieval.search("rare", collection_name="bm25_no_warn", rerank=False, hybrid=True)

    assert not [r.message for r in caplog.records if "bm25_no_warn" in r.message]


def test_detect_native_sparse_capability_is_conservative() -> None:
    """Current PersistentClient runtime should not auto-select native sparse."""
    from rag_mcp.core.retrieval.sparse import _detect_native_sparse_capability

    assert _detect_native_sparse_capability() is False


def test_sparse_backend_auto_falls_back_to_bm25_when_unsupported(monkeypatch) -> None:
    """Capability detection controls auto backend selection."""
    import rag_mcp.compose as compose
    import rag_mcp.core.retrieval.sparse as sparse
    from rag_mcp.config import Settings
    from rag_mcp.core.retrieval.settings import RetrievalSettings

    # The capability probe moved from config to compose (task 7.10): asking
    # the runtime a question is construction work, not settings data.
    settings = Settings(
        _env_file=None,
        retrieval=RetrievalSettings(hybrid_sparse_backend="auto"),
    )
    monkeypatch.setattr(sparse, "_detect_native_sparse_capability", lambda: False)

    assert compose.resolve_sparse_backend(settings) == "bm25"


def test_sparse_backend_auto_selects_native_when_supported(monkeypatch) -> None:
    """If native sparse support is detected, auto selects native."""
    import rag_mcp.compose as compose
    import rag_mcp.core.retrieval.sparse as sparse
    from rag_mcp.config import Settings
    from rag_mcp.core.retrieval.settings import RetrievalSettings

    # The capability probe moved from config to compose (task 7.10): asking
    # the runtime a question is construction work, not settings data.
    settings = Settings(
        _env_file=None,
        retrieval=RetrievalSettings(hybrid_sparse_backend="auto"),
    )
    monkeypatch.setattr(sparse, "_detect_native_sparse_capability", lambda: True)

    assert compose.resolve_sparse_backend(settings) == "native"


def test_sparse_backend_explicit_native_falls_back_to_bm25(monkeypatch, caplog) -> None:
    """Explicit native override falls back gracefully with a warning."""
    import rag_mcp.compose as compose
    import rag_mcp.core.retrieval.sparse as sparse
    from rag_mcp.config import Settings
    from rag_mcp.core.retrieval.settings import RetrievalSettings

    # The capability probe moved from config to compose (task 7.10): asking
    # the runtime a question is construction work, not settings data.
    settings = Settings(
        _env_file=None,
        retrieval=RetrievalSettings(hybrid_sparse_backend="native"),
    )
    monkeypatch.setattr(sparse, "_detect_native_sparse_capability", lambda: False)

    with caplog.at_level(logging.WARNING):
        assert compose.resolve_sparse_backend(settings) == "bm25"

    assert any("Falling back to bm25" in record.message for record in caplog.records)


def test_colosseum_style_dense_miss_recovers_with_hybrid(monkeypatch) -> None:
    """Dense top_k can miss the exact Colosseum chunk; hybrid recovers it."""
    import chromadb
    import rag_mcp.config as config
    import rag_mcp.core.retrieval.pipeline as retrieval
    import rag_mcp.core.retrieval.dense as _dense

    collection = FakeCollection(
        "colosseum_regression",
        [
            {"id": "dense_decoy", "text": "Roman venues hosted public entertainment in an ancient city.", "metadata": {"file_path": "decoy.txt"}, "distance": 0.01},
            {"id": "gold", "text": "The capital of Italy is Rome. It is known for the Colosseum.", "metadata": {"file_path": "sample.md"}, "distance": 10.0},
        ],
    )
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: FakePersistentClient({"colosseum_regression": collection}))
    monkeypatch.setattr(_dense, "_embed_query", lambda query: [0.0] * 384)
    from rag_mcp.core.settings import EffectiveSettings, RetrievalBlock, set_default_effective_settings

    set_default_effective_settings(EffectiveSettings(retrieval=RetrievalBlock(rerank_max_fetch=2, rerank_fetch_multiplier=2)))

    dense_only = retrieval.search(
        "Where was the Colosseum built?",
        collection_name="colosseum_regression",
        top_k=1,
        rerank=False,
        hybrid=False,
    )
    hybrid = retrieval.search(
        "Where was the Colosseum built?",
        collection_name="colosseum_regression",
        top_k=2,
        rerank=False,
        hybrid=True,
    )

    assert all(row["source"] != "sample.md" for row in dense_only)
    assert any(row["source"] == "sample.md" for row in hybrid)


def test_default_reranker_is_constructed_via_registry(monkeypatch) -> None:
    """When no reranker is injected, search() resolves one from the registry.

    Covers ``core/retrieval/pipeline.py``'s ``reranker = _retrieval_get("reranker")()``
    default-construction branch. The sibling injection test above passes its own
    instance, so it never exercises that line — leaving the registry-backed
    default path (introduced by this change) untested.
    """
    import chromadb
    import rag_mcp.config as config
    import rag_mcp.core.retrieval.pipeline as retrieval
    import rag_mcp.core.retrieval.dense as _dense
    import rag_mcp.core.retrieval.registry as retrieval_registry

    collection = FakeCollection(
        "documents",
        [
            {"id": "1", "text": "ZXQ-77 appears here", "metadata": {"file_path": "a.txt"}, "distance": 0.1},
            {"id": "2", "text": "unrelated text", "metadata": {"file_path": "b.txt"}, "distance": 0.9},
        ],
    )
    monkeypatch.setattr(
        chromadb, "PersistentClient", lambda **_: FakePersistentClient({"documents": collection})
    )
    monkeypatch.setattr(_dense, "_embed_query", lambda query: [0.0] * 384)

    constructed: list[str] = []

    class RecordingReranker:
        def __init__(self) -> None:
            constructed.append("built")

        def rerank(self, query: str, results: list[dict], top_k: int) -> list[dict]:
            for row in results:
                row["_reranked"] = True
            return results[:top_k]

    # Replace the registry's resolved entry, not the module attribute, so the
    # assertion fails if dispatch stops going through the registry.
    monkeypatch.setitem(retrieval_registry._cache, "reranker", RecordingReranker)

    results = retrieval.search("ZXQ-77", top_k=1, rerank=True, reranker=None)

    assert constructed == ["built"], (
        "search() did not construct the default reranker through "
        "retrieval_registry.get('reranker')"
    )
    assert results and results[0]["reranked"] is True
