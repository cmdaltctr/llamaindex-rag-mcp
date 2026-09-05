"""Tests for the OpenSpec ``rag-hybrid-retrieval`` change.

These tests intentionally pin the public contracts introduced by the
hybrid retrieval spec: opt-in API surface, RRF math, BM25 fallback
behaviour, cache invalidation, and reranker integration.
"""

from __future__ import annotations

import inspect
import logging

# ── Optional-chroma guard (task 5.1) ────────────────────────────────────
# These pipeline tests drive the hybrid paths through the ChromaDB adapter
# (EphemeralClient + fake collections). They skip by design in the base
# install and run in the chroma-extra CI job; the BM25 core tests above and
# below run against the tmp-path LanceDB default store in both installs.
from importlib.util import find_spec as _find_spec
from unittest.mock import MagicMock

import pytest

_CHROMA_EXTRA = _find_spec("chromadb") is not None
requires_chroma = pytest.mark.skipif(
    not _CHROMA_EXTRA,
    reason="chroma extra not installed (uv sync --extra chroma); runs in the chroma-extra CI job",
)


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
        rows = self.rows[offset : offset + limit] if limit is not None else self.rows
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
                metadata = metas[idx] if idx < len(metas) and isinstance(metas[idx], dict) else {}
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
    from omrg.core.retrieval import search

    param = inspect.signature(search).parameters.get("hybrid")

    assert param is not None
    assert param.default is None


def test_mcp_search_documents_signature_exposes_hybrid_opt_in() -> None:
    """The MCP tool must expose the same opt-in ``hybrid`` parameter."""
    from omrg.transports.mcp import search_documents

    param = inspect.signature(search_documents).parameters.get("hybrid")

    assert param is not None
    assert param.default is None


async def test_mcp_search_documents_passes_hybrid_through(monkeypatch) -> None:
    """MCP calls must forward ``hybrid`` unchanged to retrieval.search."""
    import omrg.transports.mcp.search as search_mod

    mock_search = MagicMock(return_value=[])
    monkeypatch.setattr(search_mod, "search", mock_search)

    from omrg.transports.mcp import search_documents

    await search_documents("needle", hybrid=True, rerank=False)

    mock_search.assert_called_once()
    assert mock_search.call_args.kwargs["hybrid"] is True


def test_hybrid_config_defaults() -> None:
    """OpenSpec defaults are stable and safe for v1 rollout."""
    import omrg.config as config

    assert config.get_settings().retrieval.hybrid_enabled is False
    assert config.get_settings().retrieval.hybrid_rrf_k == 60
    assert config.get_settings().retrieval.hybrid_sparse_backend == "bm25"


def test_rrf_worked_example_from_spec() -> None:
    """A chunk ranked 3rd and 5th scores ``1/(60+3)+1/(60+5)``."""
    from omrg.core.retrieval import reciprocal_rank_fusion

    scores = reciprocal_rank_fusion(
        [["d1", "d2", "target"], ["a", "b", "c", "d", "target"]],
        k=60,
    )

    assert scores["target"] == pytest.approx(1 / (60 + 3) + 1 / (60 + 5))


def test_rrf_chunk_present_in_only_one_ranking() -> None:
    """Missing sparse/dense ranks contribute no term to the RRF score."""
    from omrg.core.retrieval import reciprocal_rank_fusion

    scores = reciprocal_rank_fusion([["dense_only"], ["other"]], k=60)

    assert scores["dense_only"] == pytest.approx(1 / 61)
    assert scores["other"] == pytest.approx(1 / 61)


def test_rrf_with_metadata_empty_sparse_ranking_keeps_dense_order() -> None:
    """Empty sparse rankings must not error or disturb dense-only order."""
    from omrg.core.retrieval import rrf_with_metadata

    dense = [
        {"id": "a", "text": "alpha", "metadata": {"source": "a.txt"}},
        {"id": "b", "text": "beta", "metadata": {"source": "b.txt"}},
    ]

    fused = rrf_with_metadata(dense_ranked=dense, sparse_ranked=[], k=60)

    assert [row["id"] for row in fused] == ["a", "b"]
    assert all("fused_score" in row for row in fused)


def test_default_english_tokenizer_lowercases_splits_and_removes_stopwords() -> None:
    """BM25 tokenisation should be deterministic and useful for rare terms."""
    from omrg.core.retrieval.sparse import tokenize_english

    tokens = tokenize_english("The Colosseum identifier ZXQ-77 appears in Rome.")

    assert "the" not in tokens
    assert "in" not in tokens
    assert "colosseum" in tokens
    assert "zxq" in tokens
    assert "77" in tokens
    assert all(token == token.lower() for token in tokens)


def test_bm25_sparse_retriever_empty_collection_returns_empty() -> None:
    """The BM25 fallback must gracefully handle empty collections."""
    from omrg.core.retrieval.sparse import BM25SparseRetriever

    collection = FakeCollection("empty", [])
    store = FakeStore(collection)
    retriever = BM25SparseRetriever(collection_name="empty", store=store)

    assert retriever.query("anything", top_n=5) == []


def test_bm25_sparse_retriever_ranks_exact_rare_term_first() -> None:
    """Rare exact-match identifiers should be promoted by BM25."""
    from omrg.core.retrieval.sparse import BM25SparseRetriever

    collection = FakeCollection(
        "rare_terms",
        [
            {
                "id": "semantic",
                "text": "Ancient amphitheatres hosted spectacles.",
                "metadata": {"file_path": "semantic.txt"},
            },
            {
                "id": "rare",
                "text": "The continuity note contains ZXQ-77 for the Colosseum.",
                "metadata": {"file_path": "rare.txt"},
            },
            {
                "id": "noise",
                "text": "Modern stadium design uses concrete.",
                "metadata": {"file_path": "noise.txt"},
            },
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
    from omrg.core.retrieval.sparse import BM25SparseRetriever

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
    from omrg.core.retrieval.sparse import BM25SparseRetriever

    collection = FakeCollection(
        "cache_rebuild",
        [
            {"id": "old", "text": "old token", "metadata": {}},
            {"id": "fill1", "text": "filler alpha content", "metadata": {}},
            {"id": "fill2", "text": "filler beta content", "metadata": {}},
        ],
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
    from omrg.core.retrieval.sparse import BM25SparseRetriever

    collection = FakeCollection(
        "delete_rebuild",
        [
            {"id": "gone", "text": "raredelete token", "metadata": {}},
            {"id": "fill1", "text": "filler alpha content", "metadata": {}},
            {"id": "fill2", "text": "filler beta content", "metadata": {}},
        ],
    )
    store = FakeStore(collection)
    store._generations["delete_rebuild"] = 0
    retriever = BM25SparseRetriever("delete_rebuild", store=store)

    assert [row[1] for row in retriever.query("raredelete", top_n=5)] == ["gone"]
    collection.rows.clear()
    store.bump_generation("delete_rebuild")

    assert retriever.query("raredelete", top_n=5) == []
    # Task 3.2 of fix-retrieval-freshness: the cache stores the tagged
    # validity token, not the bare generation, so mode transitions
    # (durable <-> process-local fallback) can never compare equal.
    from omrg.core.retrieval.sparse import _LOCAL_TOKEN_PREFIX

    assert (
        BM25SparseRetriever._cache[(store, "delete_rebuild")].validity_token
        == f"{_LOCAL_TOKEN_PREFIX}:1"
    )


def test_bm25_cache_namespaces_same_collection_by_store() -> None:
    """Two stores with equal generations cannot contaminate each other."""
    from omrg.core.retrieval.sparse import BM25SparseRetriever

    store_a = FakeStore(
        FakeCollection(
            "shared",
            [
                {"id": "a", "text": "alpha unique token", "metadata": {}},
                {"id": "a1", "text": "filler one", "metadata": {}},
                {"id": "a2", "text": "filler two", "metadata": {}},
            ],
        )
    )
    store_b = FakeStore(
        FakeCollection(
            "shared",
            [
                {"id": "b", "text": "beta unique token", "metadata": {}},
                {"id": "b1", "text": "filler one", "metadata": {}},
                {"id": "b2", "text": "filler two", "metadata": {}},
            ],
        )
    )

    assert BM25SparseRetriever("shared", store=store_a).query("alpha", 1)[0][1] == "a"
    assert BM25SparseRetriever("shared", store=store_b).query("beta", 1)[0][1] == "b"
    assert (store_a, "shared") in BM25SparseRetriever._cache
    assert (store_b, "shared") in BM25SparseRetriever._cache


@requires_chroma
def test_two_chroma_store_instances_do_not_share_bm25_rows() -> None:
    """Two Chroma adapters with the same collection name stay isolated."""
    from omrg.core.retrieval.sparse import BM25SparseRetriever
    from omrg.core.vectordb.chroma import ChromaVectorStore

    client_a = FakePersistentClient(
        {
            "shared_chroma": FakeCollection(
                "shared_chroma",
                [
                    {"id": "a", "text": "alpha unique", "metadata": {}},
                    {"id": "a1", "text": "filler gamma", "metadata": {}},
                    {"id": "a2", "text": "filler delta", "metadata": {}},
                ],
            )
        }
    )
    client_b = FakePersistentClient(
        {
            "shared_chroma": FakeCollection(
                "shared_chroma",
                [
                    {"id": "b", "text": "beta unique", "metadata": {}},
                    {"id": "b1", "text": "filler gamma", "metadata": {}},
                    {"id": "b2", "text": "filler delta", "metadata": {}},
                ],
            )
        }
    )
    store_a = ChromaVectorStore(client=client_a)
    store_b = ChromaVectorStore(client=client_b)

    assert BM25SparseRetriever("shared_chroma", store=store_a).query("alpha", 1)[0][1] == "a"
    assert BM25SparseRetriever("shared_chroma", store=store_b).query("beta", 1)[0][1] == "b"


def test_bm25_metadata_filter_supports_nested_and_operator_shapes() -> None:
    """Sparse eligibility matches the filter shapes shared by both stores."""
    from omrg.core.retrieval.sparse import BM25SparseRetriever

    store = FakeStore(
        FakeCollection(
            "filtered",
            [
                {
                    "id": "allowed",
                    "text": "needle allowed",
                    "metadata": {"category": "allowed", "priority": 3},
                },
                {
                    "id": "forbidden",
                    "text": "needle needle forbidden",
                    "metadata": {"category": "forbidden", "priority": 9},
                },
                {
                    "id": "other",
                    "text": "unrelated filler",
                    "metadata": {"category": "allowed", "priority": 1},
                },
            ],
        )
    )
    rows = BM25SparseRetriever("filtered", store=store).query(
        "needle",
        5,
        metadata_filter={
            "$and": [
                {"category": {"$in": ["allowed"]}},
                {"priority": {"$gte": 2}},
            ]
        },
    )

    assert [row[1] for row in rows] == ["allowed"]


def test_hybrid_filter_cannot_reintroduce_forbidden_sparse_row(monkeypatch) -> None:
    """RRF receives only sparse rows satisfying the caller constraint."""
    import omrg.core.retrieval.pipeline as pipeline
    import omrg.core.retrieval.registry as registry
    from omrg.core.settings import EffectiveSettings, RetrievalBlock

    store = FakeStore(
        FakeCollection(
            "hybrid_filter",
            [
                {
                    "id": "allowed",
                    "text": "needle allowed",
                    "metadata": {"category": "allowed"},
                },
                {
                    "id": "forbidden",
                    "text": "needle needle forbidden",
                    "metadata": {"category": "forbidden"},
                },
                {"id": "filler", "text": "unrelated filler", "metadata": {}},
            ],
        )
    )

    def filtered_dense(*args, **kwargs):
        assert args[-1] == {"category": "allowed"}
        return [
            {
                "id": "allowed",
                "text": "needle allowed",
                "metadata": {"category": "allowed"},
                "score": 0.9,
                "score_kind": "dense_similarity_v1",
                "reranked": False,
            }
        ]

    monkeypatch.setitem(registry._cache, "dense", filtered_dense)
    rows = pipeline._hybrid_query_rows(
        store,
        "hybrid_filter",
        "needle",
        3,
        60,
        EffectiveSettings(retrieval=RetrievalBlock(hybrid_sparse_backend="bm25")),
        metadata_filter={"category": "allowed"},
    )

    assert [row["id"] for row in rows] == ["allowed"]


def test_positive_dense_threshold_filters_before_nonreranked_fusion(monkeypatch) -> None:
    """Sparse-only and low-dense rows cannot satisfy a dense minimum."""
    import omrg.core.retrieval.pipeline as pipeline
    import omrg.core.retrieval.registry as registry
    from omrg.core.settings import EffectiveSettings, RetrievalBlock

    store = FakeStore(
        FakeCollection(
            "threshold",
            [
                {"id": "qualifies", "text": "needle qualifies", "metadata": {}},
                {"id": "low", "text": "needle low", "metadata": {}},
                {"id": "sparse", "text": "needle sparse only", "metadata": {}},
            ],
        )
    )

    def dense_rows(*args, **kwargs):
        return [
            {
                "id": "qualifies",
                "text": "needle qualifies",
                "metadata": {},
                "score": 0.9,
                "score_kind": "dense_similarity_v1",
                "reranked": False,
            },
            {
                "id": "low",
                "text": "needle low",
                "metadata": {},
                "score": 0.2,
                "score_kind": "dense_similarity_v1",
                "reranked": False,
            },
        ]

    monkeypatch.setitem(registry._cache, "dense", dense_rows)
    rows = pipeline._hybrid_query_rows(
        store,
        "threshold",
        "needle",
        3,
        60,
        EffectiveSettings(retrieval=RetrievalBlock(hybrid_sparse_backend="bm25")),
        dense_threshold=0.3,
    )

    assert [row["id"] for row in rows] == ["qualifies"]


def test_hybrid_rerank_success_thresholds_reranker_score(monkeypatch) -> None:
    """Successful reranking switches threshold semantics from RRF to reranker."""
    import omrg.core.retrieval.pipeline as pipeline
    from omrg.core.settings import EffectiveSettings

    monkeypatch.setattr(
        pipeline,
        "_hybrid_query_rows",
        lambda *args, **kwargs: [
            {
                "id": "candidate",
                "source": "candidate.txt",
                "page_label": None,
                "text": "candidate",
                "metadata": {},
                "score": 0.02,
                "score_kind": "rrf_v1",
                "reranked": False,
            }
        ],
    )

    class SuccessfulReranker:
        def rerank(self, query, results, top_k):
            results[0]["score"] = 0.02
            results[0]["_reranked"] = True
            return results

    store = MagicMock()
    store.count.return_value = 1
    rows = pipeline.search(
        "candidate",
        top_k=1,
        similarity_threshold=0.3,
        rerank=True,
        hybrid=True,
        reranker=SuccessfulReranker(),
        store=store,
        effective_settings=EffectiveSettings(),
        include_diagnostics=True,
    )

    assert len(rows) == 1
    assert rows[0]["score_kind"] == "reranker_sigmoid_v1"
    assert rows[0]["threshold_score_kind"] == "reranker_sigmoid_v1"


def test_hybrid_rerank_failure_restores_dense_threshold_semantics(monkeypatch) -> None:
    """A failed reranker rebuilds hybrid candidates under the dense rule."""
    import omrg.core.retrieval.pipeline as pipeline
    from omrg.core.settings import EffectiveSettings

    thresholds: list[float] = []

    def hybrid_rows(*args, **kwargs):
        threshold = args[-1]
        thresholds.append(threshold)
        return [
            {
                "id": "candidate",
                "source": "candidate.txt",
                "page_label": None,
                "text": "candidate",
                "metadata": {},
                "score": 0.03,
                "score_kind": "rrf_v1",
                "dense_score": 0.9,
                "reranked": False,
            }
        ]

    monkeypatch.setattr(pipeline, "_hybrid_query_rows", hybrid_rows)

    class FailedReranker:
        last_failure_reason = "inference failed"

        def rerank(self, query, results, top_k):
            results[0]["_reranked"] = False
            return results

    store = MagicMock()
    store.count.return_value = 1
    rows = pipeline.search(
        "candidate",
        top_k=1,
        similarity_threshold=0.3,
        rerank=True,
        hybrid=True,
        reranker=FailedReranker(),
        store=store,
        effective_settings=EffectiveSettings(),
        include_diagnostics=True,
    )

    assert thresholds == [0.0, 0.3]
    assert len(rows) == 1
    assert rows[0]["threshold_score_kind"] == "dense_similarity_v1"


def test_remove_collection_generation_invalidates_cache() -> None:
    """Collection removal generation bump invalidates the cached BM25 index."""
    from omrg.core.retrieval.sparse import BM25SparseRetriever

    collection = FakeCollection(
        "drop_rebuild",
        [
            {"id": "old", "text": "dropme token", "metadata": {}},
            {"id": "fill1", "text": "filler alpha content", "metadata": {}},
            {"id": "fill2", "text": "filler beta content", "metadata": {}},
        ],
    )
    store = FakeStore(collection)
    store._generations["drop_rebuild"] = 0
    retriever = BM25SparseRetriever("drop_rebuild", store=store)

    retriever.query("dropme", top_n=5)
    collection.rows[:] = [
        {"id": "new", "text": "replacement token", "metadata": {}},
        {"id": "fill1", "text": "filler alpha content", "metadata": {}},
        {"id": "fill2", "text": "filler beta content", "metadata": {}},
    ]
    store.bump_generation("drop_rebuild")

    assert [row[1] for row in retriever.query("replacement", top_n=5)] == ["new"]


@requires_chroma
def test_hybrid_false_matches_dense_only_result_shape(monkeypatch) -> None:
    """The dense-only default must remain byte-for-byte compatible."""
    import chromadb

    import omrg.core.retrieval.dense as _dense
    import omrg.core.retrieval.pipeline as retrieval

    collection = FakeCollection(
        "documents",
        [
            {
                "id": "dense",
                "text": "dense text",
                "metadata": {"file_path": "dense.txt"},
                "distance": 1.0,
            }
        ],
    )
    client = FakePersistentClient({"documents": collection})
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: client)
    from omrg.core.vectordb.chroma import ChromaVectorStore

    chroma_store = ChromaVectorStore(client=client)
    monkeypatch.setattr(
        _dense, "_embed_query", lambda query, embed_model=None, cache=None: [0.0] * 384
    )

    implicit = retrieval.search("query", top_k=1, rerank=False, store=chroma_store)
    explicit = retrieval.search("query", top_k=1, rerank=False, hybrid=False, store=chroma_store)

    assert explicit == implicit


@requires_chroma
def test_hybrid_rerank_receives_fused_sparse_candidate(monkeypatch) -> None:
    """Hybrid + rerank must feed the reranker the fused dense+sparse pool."""
    import chromadb

    import omrg.core.retrieval.dense as _dense
    import omrg.core.retrieval.pipeline as retrieval

    dense_rows = [
        {
            "id": "dense",
            "text": "semantic amphitheatre",
            "metadata": {"file_path": "dense.txt"},
            "distance": 0.1,
        },
        {
            "id": "sparse",
            "text": "ZXQ-77 exact identifier",
            "metadata": {"file_path": "sparse.txt"},
            "distance": 9.0,
        },
    ]
    collection = FakeCollection("documents", dense_rows)
    client = FakePersistentClient({"documents": collection})
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: client)
    from omrg.core.vectordb.chroma import ChromaVectorStore

    chroma_store = ChromaVectorStore(client=client)
    monkeypatch.setattr(
        _dense, "_embed_query", lambda query, embed_model=None, cache=None: [0.0] * 384
    )
    from omrg.core.settings import (
        EffectiveSettings,
        RetrievalBlock,
        set_default_effective_settings,
    )

    set_default_effective_settings(
        EffectiveSettings(retrieval=RetrievalBlock(rerank_max_fetch=2, rerank_fetch_multiplier=2))
    )

    captured: dict[str, list[dict]] = {}

    class CapturingReranker:
        def rerank(self, query: str, results: list[dict], top_k: int) -> list[dict]:
            captured["results"] = [dict(row) for row in results]
            for row in results:
                row["_reranked"] = True
            return results[:top_k]

    # Inject the capturing reranker directly via the DI parameter.
    retrieval.search(
        "ZXQ-77",
        top_k=1,
        rerank=True,
        hybrid=True,
        reranker=CapturingReranker(),
        store=chroma_store,
    )

    assert "results" in captured
    assert any(row["source"] == "sparse.txt" for row in captured["results"])
    assert len(captured["results"]) == 2


@requires_chroma
def test_hybrid_public_shape_strips_rank_diagnostics(monkeypatch) -> None:
    """MCP/CLI public result shape should not leak internal fusion fields."""
    import chromadb

    import omrg.core.retrieval.dense as _dense
    import omrg.core.retrieval.pipeline as retrieval

    collection = FakeCollection(
        "documents",
        [
            {
                "id": "dense",
                "text": "semantic amphitheatre",
                "metadata": {"file_path": "dense.txt"},
                "distance": 0.1,
            },
            {
                "id": "sparse",
                "text": "Colosseum exact identifier",
                "metadata": {"file_path": "sparse.txt"},
                "distance": 9.0,
            },
        ],
    )
    client = FakePersistentClient({"documents": collection})
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: client)
    from omrg.core.vectordb.chroma import ChromaVectorStore

    chroma_store = ChromaVectorStore(client=client)
    monkeypatch.setattr(
        _dense, "_embed_query", lambda query, embed_model=None, cache=None: [0.0] * 384
    )
    from omrg.core.settings import (
        EffectiveSettings,
        RetrievalBlock,
        set_default_effective_settings,
    )

    set_default_effective_settings(
        EffectiveSettings(retrieval=RetrievalBlock(rerank_max_fetch=2, rerank_fetch_multiplier=2))
    )

    public_results = retrieval.search(
        "Colosseum", top_k=2, rerank=False, hybrid=True, store=chroma_store
    )

    assert public_results
    for result in public_results:
        assert "id" not in result
        assert "fused_score" not in result
        assert "dense_rank" not in result
        assert "sparse_rank" not in result
        assert "fused_rank" not in result


@requires_chroma
def test_hybrid_diagnostics_are_available_for_experiments(monkeypatch) -> None:
    """Experiment 9 can opt into fusion rank diagnostics explicitly."""
    import chromadb

    import omrg.core.retrieval.dense as _dense
    import omrg.core.retrieval.pipeline as retrieval

    collection = FakeCollection(
        "documents",
        [
            {
                "id": "target",
                "text": "Colosseum exact identifier",
                "metadata": {"file_path": "target.txt"},
                "distance": 5.0,
            }
        ],
    )
    client = FakePersistentClient({"documents": collection})
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: client)
    from omrg.core.vectordb.chroma import ChromaVectorStore

    chroma_store = ChromaVectorStore(client=client)
    monkeypatch.setattr(
        _dense, "_embed_query", lambda query, embed_model=None, cache=None: [0.0] * 384
    )
    from omrg.core.settings import (
        EffectiveSettings,
        RetrievalBlock,
        set_default_effective_settings,
    )

    set_default_effective_settings(
        EffectiveSettings(retrieval=RetrievalBlock(rerank_max_fetch=1, rerank_fetch_multiplier=1))
    )

    results = retrieval.search(
        "Colosseum",
        top_k=1,
        rerank=False,
        hybrid=True,
        include_diagnostics=True,
        store=chroma_store,
    )

    assert results[0]["id"] == "target"
    assert "sparse_rank" in results[0]
    assert results[0]["fused_rank"] == 1


@requires_chroma
def test_native_mixed_coverage_warning_is_one_shot(monkeypatch, caplog) -> None:
    """Native sparse mixed coverage should warn once with remediation text."""
    import chromadb

    import omrg.core.retrieval.dense as _dense
    import omrg.core.retrieval.pipeline as retrieval

    collection = FakeCollection(
        "mixed_native",
        [
            {
                "id": "with_sparse",
                "text": "has sparse",
                "metadata": {"file_path": "a.txt", "has_sparse_vector": True},
            },
            {"id": "without_sparse", "text": "missing sparse", "metadata": {"file_path": "b.txt"}},
        ],
    )
    client = FakePersistentClient({"mixed_native": collection})
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: client)
    from omrg.core.vectordb.chroma import ChromaVectorStore

    chroma_store = ChromaVectorStore(client=client)
    monkeypatch.setattr(
        _dense, "_embed_query", lambda query, embed_model=None, cache=None: [0.0] * 384
    )
    from omrg.core.settings import (
        EffectiveSettings,
        RetrievalBlock,
        set_default_effective_settings,
    )

    set_default_effective_settings(
        EffectiveSettings(retrieval=RetrievalBlock(hybrid_sparse_backend="native"))
    )
    monkeypatch.setattr(retrieval, "_selected_sparse_backend", lambda _s: "native")
    if hasattr(retrieval, "_warned_collections"):
        retrieval._warned_collections.clear()
    if hasattr(retrieval, "_warned_native_fallback_collections"):
        retrieval._warned_native_fallback_collections.clear()

    with caplog.at_level(logging.WARNING):
        retrieval.search(
            "query", collection_name="mixed_native", rerank=False, hybrid=True, store=chroma_store
        )
        retrieval.search(
            "query", collection_name="mixed_native", rerank=False, hybrid=True, store=chroma_store
        )

    warnings = [
        r.message
        for r in caplog.records
        if "mixed_native" in r.message and "mixed coverage" in r.message
    ]
    assert len(warnings) == 1
    assert "re-ingest" in warnings[0].lower() or "reingest" in warnings[0].lower()


@requires_chroma
def test_mixed_coverage_warning_uses_paged_metadata_scan(monkeypatch, caplog) -> None:
    """Native coverage checks must respect CHROMA_SCAN_PAGE_SIZE paging."""
    import chromadb

    import omrg.core.retrieval.dense as _dense
    import omrg.core.retrieval.pipeline as retrieval

    rows = [
        {
            "id": "with_sparse",
            "text": "has sparse",
            "metadata": {"file_path": "a.txt", "has_sparse_vector": True},
        },
        {"id": "without_sparse", "text": "missing sparse", "metadata": {"file_path": "b.txt"}},
        {
            "id": "without_sparse_2",
            "text": "missing sparse again",
            "metadata": {"file_path": "c.txt"},
        },
    ]
    collection = FakeCollection("paged_native", rows)
    client = FakePersistentClient({"paged_native": collection})
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: client)
    from omrg.core.vectordb.chroma import ChromaVectorStore

    chroma_store = ChromaVectorStore(client=client, scan_page_size=1)
    monkeypatch.setattr(
        _dense, "_embed_query", lambda query, embed_model=None, cache=None: [0.0] * 384
    )
    monkeypatch.setattr(retrieval, "_selected_sparse_backend", lambda _s: "native")
    retrieval._warned_collections.clear()
    retrieval._warned_native_fallback_collections.clear()

    with caplog.at_level(logging.WARNING):
        retrieval.search(
            "query", collection_name="paged_native", rerank=False, hybrid=True, store=chroma_store
        )

    assert collection.get_calls >= 3
    assert any("1/3 chunks" in record.message for record in caplog.records)


@requires_chroma
def test_native_sparse_placeholder_falls_back_to_bm25_not_dense_only(monkeypatch, caplog) -> None:
    """Selected native without real query support must use BM25 sparse results."""
    import chromadb

    import omrg.core.retrieval.dense as _dense
    import omrg.core.retrieval.pipeline as retrieval

    collection = FakeCollection(
        "native_fallback",
        [
            {
                "id": "dense",
                "text": "generic amphitheatre",
                "metadata": {"file_path": "dense.txt"},
                "distance": 0.1,
            },
            {
                "id": "bm25",
                "text": "Colosseum exact rare term",
                "metadata": {"file_path": "bm25.txt"},
                "distance": 9.0,
            },
            {
                "id": "filler",
                "text": "modern stadium concrete design",
                "metadata": {"file_path": "filler.txt"},
                "distance": 5.0,
            },
        ],
    )
    from omrg.core.settings import (
        EffectiveSettings,
        RetrievalBlock,
        set_default_effective_settings,
    )

    set_default_effective_settings(
        EffectiveSettings(retrieval=RetrievalBlock(rerank_max_fetch=2, rerank_fetch_multiplier=2))
    )
    client = FakePersistentClient({"native_fallback": collection})
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: client)
    from omrg.core.vectordb.chroma import ChromaVectorStore

    chroma_store = ChromaVectorStore(client=client)
    monkeypatch.setattr(
        _dense, "_embed_query", lambda query, embed_model=None, cache=None: [0.0] * 384
    )
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
            store=chroma_store,
        )

    assert any(row["source"] == "bm25.txt" and row["sparse_rank"] == 1 for row in results)
    assert any(
        "Falling back to the BM25 sparse retriever" in record.message for record in caplog.records
    )


@requires_chroma
def test_bm25_path_suppresses_mixed_coverage_warning(monkeypatch, caplog) -> None:
    """BM25 indexes all chunks it sees and must not warn about sparse coverage."""
    import chromadb

    import omrg.core.retrieval.dense as _dense
    import omrg.core.retrieval.pipeline as retrieval

    collection = FakeCollection(
        "bm25_no_warn",
        [
            {"id": "a", "text": "rare token", "metadata": {"file_path": "a.txt"}},
            {
                "id": "b",
                "text": "other token",
                "metadata": {"file_path": "b.txt", "has_sparse_vector": True},
            },
        ],
    )
    client = FakePersistentClient({"bm25_no_warn": collection})
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: client)
    from omrg.core.vectordb.chroma import ChromaVectorStore

    chroma_store = ChromaVectorStore(client=client)
    monkeypatch.setattr(
        _dense, "_embed_query", lambda query, embed_model=None, cache=None: [0.0] * 384
    )
    monkeypatch.setattr(retrieval, "_selected_sparse_backend", lambda _s: "bm25")

    with caplog.at_level(logging.WARNING):
        retrieval.search(
            "rare", collection_name="bm25_no_warn", rerank=False, hybrid=True, store=chroma_store
        )

    assert not [r.message for r in caplog.records if "bm25_no_warn" in r.message]


def test_sparse_backend_auto_falls_back_to_bm25_when_unsupported(monkeypatch) -> None:
    """Capability detection controls auto backend selection.

    Store-neutral resolution (task 3.2,
    implement-native-sparse-backend-strategy): ``auto`` resolves through
    the selected store's registry metadata plus a real native-FTS
    probe. A store that declares no native sparse capability (the
    quarantined Chroma extra) resolves ``auto`` to ``bm25`` without
    emitting the explicit-native fallback warning.
    """
    import omrg.compose as compose
    from omrg.config import Settings
    from omrg.core.retrieval.settings import RetrievalSettings

    settings = Settings(
        _env_file=None,
        vector_store="chroma",
        retrieval=RetrievalSettings(hybrid_sparse_backend="auto"),
    )

    assert compose.resolve_sparse_backend(settings) == "bm25"


def test_sparse_backend_auto_selects_native_when_supported(monkeypatch) -> None:
    """If native sparse support is detected, auto selects native.

    The lancedb registry entry carries the real native-FTS probe; on
    the locked runtime (lancedb 0.37.1) it reports availability.
    """
    import omrg.compose as compose
    from omrg.config import Settings
    from omrg.core.retrieval.settings import RetrievalSettings

    settings = Settings(
        _env_file=None,
        vector_store="lancedb",
        retrieval=RetrievalSettings(hybrid_sparse_backend="auto"),
    )

    assert compose.resolve_sparse_backend(settings) == "native"


def test_sparse_backend_auto_respects_a_failing_probe(monkeypatch) -> None:
    """A probe that reports unavailability resolves auto to bm25."""
    import omrg.compose as compose
    import omrg.core.vectordb.lance_fts as lance_fts
    from omrg.config import Settings
    from omrg.core.retrieval.settings import RetrievalSettings

    settings = Settings(
        _env_file=None,
        vector_store="lancedb",
        retrieval=RetrievalSettings(hybrid_sparse_backend="auto"),
    )
    monkeypatch.setattr(lance_fts, "probe_native_fts", lambda: False)

    assert compose.resolve_sparse_backend(settings) == "bm25"


def test_sparse_backend_explicit_native_falls_back_to_bm25(monkeypatch, caplog) -> None:
    """Explicit native override falls back gracefully with a warning."""
    import omrg.compose as compose
    from omrg.config import Settings
    from omrg.core.retrieval.settings import RetrievalSettings

    settings = Settings(
        _env_file=None,
        vector_store="chroma",
        retrieval=RetrievalSettings(hybrid_sparse_backend="native"),
    )

    with caplog.at_level(logging.WARNING):
        assert compose.resolve_sparse_backend(settings) == "bm25"

    assert any("Falling back to bm25" in record.message for record in caplog.records)


def test_sparse_backend_unknown_name_fails_listing_registered_names() -> None:
    """An unregistered concrete name fails listing auto plus the registry.

    Composition-boundary validation (task 3.5): the accepted set is
    registry-owned, ``auto`` stays a separately accepted policy name,
    and the error lists it alongside the registered concrete names.
    """
    import omrg.compose as compose
    from omrg.config import Settings
    from omrg.core.retrieval.settings import RetrievalSettings

    settings = Settings(
        _env_file=None,
        vector_store="lancedb",
        retrieval=RetrievalSettings(hybrid_sparse_backend="tantivy"),
    )

    with pytest.raises(ValueError, match="tantivy"):
        compose.resolve_sparse_backend(settings)


@requires_chroma
def test_colosseum_style_dense_miss_recovers_with_hybrid(monkeypatch) -> None:
    """Dense top_k can miss the exact Colosseum chunk; hybrid recovers it."""
    import chromadb

    import omrg.core.retrieval.dense as _dense
    import omrg.core.retrieval.pipeline as retrieval

    collection = FakeCollection(
        "colosseum_regression",
        [
            {
                "id": "dense_decoy",
                "text": "Roman venues hosted public entertainment in an ancient city.",
                "metadata": {"file_path": "decoy.txt"},
                "distance": 0.01,
            },
            {
                "id": "gold",
                "text": "The capital of Italy is Rome. It is known for the Colosseum.",
                "metadata": {"file_path": "sample.md"},
                "distance": 10.0,
            },
        ],
    )
    client = FakePersistentClient({"colosseum_regression": collection})
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: client)
    from omrg.core.vectordb.chroma import ChromaVectorStore

    chroma_store = ChromaVectorStore(client=client)
    monkeypatch.setattr(
        _dense, "_embed_query", lambda query, embed_model=None, cache=None: [0.0] * 384
    )
    from omrg.core.settings import (
        EffectiveSettings,
        RetrievalBlock,
        set_default_effective_settings,
    )

    set_default_effective_settings(
        EffectiveSettings(retrieval=RetrievalBlock(rerank_max_fetch=2, rerank_fetch_multiplier=2))
    )

    dense_only = retrieval.search(
        "Where was the Colosseum built?",
        collection_name="colosseum_regression",
        top_k=1,
        rerank=False,
        hybrid=False,
        store=chroma_store,
    )
    hybrid = retrieval.search(
        "Where was the Colosseum built?",
        collection_name="colosseum_regression",
        top_k=2,
        rerank=False,
        hybrid=True,
        store=chroma_store,
    )

    assert all(row["source"] != "sample.md" for row in dense_only)
    assert any(row["source"] == "sample.md" for row in hybrid)


@requires_chroma
def test_default_reranker_is_constructed_via_registry(monkeypatch) -> None:
    """When no reranker is injected, search() resolves one from the registry.

    Covers ``core/retrieval/pipeline.py``'s ``reranker = _retrieval_get("reranker")()``
    default-construction branch. The sibling injection test above passes its own
    instance, so it never exercises that line — leaving the registry-backed
    default path (introduced by this change) untested.
    """
    import chromadb

    import omrg.core.retrieval.dense as _dense
    import omrg.core.retrieval.pipeline as retrieval
    import omrg.core.retrieval.registry as retrieval_registry

    collection = FakeCollection(
        "documents",
        [
            {
                "id": "1",
                "text": "ZXQ-77 appears here",
                "metadata": {"file_path": "a.txt"},
                "distance": 0.1,
            },
            {
                "id": "2",
                "text": "unrelated text",
                "metadata": {"file_path": "b.txt"},
                "distance": 0.9,
            },
        ],
    )
    client = FakePersistentClient({"documents": collection})
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_: client)
    from omrg.core.vectordb.chroma import ChromaVectorStore

    chroma_store = ChromaVectorStore(client=client)
    monkeypatch.setattr(
        _dense, "_embed_query", lambda query, embed_model=None, cache=None: [0.0] * 384
    )

    constructed: list[str] = []

    class RecordingReranker:
        def __init__(self, model_id: str | None = None) -> None:
            constructed.append("built")

        def rerank(self, query: str, results: list[dict], top_k: int) -> list[dict]:
            for row in results:
                row["_reranked"] = True
            return results[:top_k]

    # Replace the registry's resolved entry, not the module attribute, so the
    # assertion fails if dispatch stops going through the registry.  The cache
    # key changed from "reranker" to "reranker_onnx" when the bare name was
    # retired (design decision 4).
    monkeypatch.setitem(retrieval_registry._cache, "reranker_onnx", RecordingReranker)

    results = retrieval.search("ZXQ-77", top_k=1, rerank=True, reranker=None, store=chroma_store)

    assert constructed == ["built"], (
        "search() did not construct the default reranker through the registry"
    )
    assert results and results[0]["reranked"] is True
