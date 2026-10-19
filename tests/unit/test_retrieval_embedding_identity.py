"""Retrieval and answer pass a supplied embedding identity to the store (ADR-081).

A fake store records the keyword arguments of ``query_dense`` and
``query_native_sparse``. ``embedding_identity`` must reach both, and must be
absent when the caller supplies none, so stores without the keyword keep
working.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from omrg.core.vectordb.identity import EmbeddingIdentity

IDENTITY_B = EmbeddingIdentity(provider="ollama", model="model-b")
_ROW = {
    "id": "chunk-1",
    "score": 1.0,
    "score_kind": "dense_similarity_v1",
    "document": "stored evidence",
    "metadata": {"file_path": "evidence.md"},
}


class _RecordingEmbedding:
    model_name = "model-b"

    def get_query_embedding(self, text: str) -> list[float]:
        return [1.0, 0.0]


class _RecordingStore:
    cache_identity = "recording-store"

    def __init__(self) -> None:
        self.dense_kwargs: list[dict[str, Any]] = []
        self.sparse_kwargs: list[dict[str, Any]] = []

    def count(self, _collection_name: str) -> int:
        return 1

    def query_dense(self, **kwargs: Any) -> list[dict]:
        self.dense_kwargs.append(kwargs)
        return [dict(_ROW)]

    def query_native_sparse(self, *args: Any, **kwargs: Any) -> list[dict]:
        self.sparse_kwargs.append(kwargs)
        return [dict(_ROW, score_kind="native_fts_v1")]

    def close(self) -> None:
        return None


def _search(store: _RecordingStore, settings: Any, **extra: Any) -> list[dict]:
    from omrg.core.retrieval.pipeline import search

    return search(
        "what proves the theorem",
        collection_name="docs",
        store=store,
        effective_settings=settings,
        embed_model=_RecordingEmbedding(),
        rerank=False,
        **extra,
    )


def test_dense_search_passes_identity_to_the_store(effective_settings) -> None:
    store = _RecordingStore()
    _search(store, effective_settings(hybrid_enabled=False), embedding_identity=IDENTITY_B)
    assert store.dense_kwargs[0]["embedding_identity"] == IDENTITY_B


def test_hybrid_native_search_passes_identity_to_dense_and_sparse(effective_settings) -> None:
    store = _RecordingStore()
    settings = effective_settings(
        hybrid_enabled=True, hybrid_sparse_backend="native", similarity_threshold=0.0
    )
    _search(store, settings, embedding_identity=IDENTITY_B)
    assert store.dense_kwargs[0]["embedding_identity"] == IDENTITY_B
    assert store.sparse_kwargs[0]["embedding_identity"] == IDENTITY_B


def test_search_without_identity_sends_no_identity_keyword(effective_settings) -> None:
    store = _RecordingStore()
    settings = effective_settings(hybrid_enabled=True, hybrid_sparse_backend="native")
    _search(store, settings)
    assert "embedding_identity" not in store.dense_kwargs[0]
    assert "embedding_identity" not in store.sparse_kwargs[0]


def test_search_retriever_passes_identity_to_search_fn() -> None:
    from omrg.core.answer.retriever import SearchRetriever

    captured: dict[str, Any] = {}

    def fake_search(query: str, **kwargs: Any) -> list[dict]:
        captured.update(kwargs)
        return []

    SearchRetriever(search_fn=fake_search, embedding_identity=IDENTITY_B).retrieve("q")
    assert captured["embedding_identity"] == IDENTITY_B


def test_search_retriever_without_identity_adds_no_keyword() -> None:
    from omrg.core.answer.retriever import SearchRetriever

    captured: dict[str, Any] = {}

    def fake_search(query: str, **kwargs: Any) -> list[dict]:
        captured.update(kwargs)
        return []

    SearchRetriever(search_fn=fake_search).retrieve("q")
    assert "embedding_identity" not in captured


def test_answer_hands_identity_to_the_retriever(
    effective_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrg.core.answer import pipeline as answer_pipeline

    seen: dict[str, Any] = {}

    class _Spy(answer_pipeline.SearchRetriever):
        def __init__(self, **kwargs: Any) -> None:
            seen.update(kwargs)
            super().__init__(**kwargs)

        def retrieve(self, *_args: Any, **_kwargs: Any) -> list:
            raise RuntimeError("stop after construction")

    monkeypatch.setattr(answer_pipeline, "SearchRetriever", _Spy)
    asyncio.run(
        answer_pipeline.answer(
            "q",
            effective_settings=effective_settings(),
            embedding_identity=IDENTITY_B,
            store=_RecordingStore(),
        )
    )
    assert seen["embedding_identity"] == IDENTITY_B
