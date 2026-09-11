"""Red-first tests for query embedding preparation and cache semantics.

OpenSpec: improve-rag-input-quality-5, tasks 4.1-4.8.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, cast

import pytest
from llama_index.core.schema import MetadataMode, TextNode

from omrg.core.settings import EffectiveSettings, EmbeddingBlock, MetadataBlock, RetrievalBlock

INSTRUCTION = "Retrieve passages that answer the question."
RAW_QUERY = "What proves the theorem?"
PREPARED_QUERY = f"Instruct: {INSTRUCTION}\nQuery: {RAW_QUERY}"


class _RecordingEmbedding:
    """Embedding double that records model-facing query and document text."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.query_inputs: list[str] = []
        self.document_inputs: list[str] = []

    def get_query_embedding(self, text: str) -> list[float]:
        self.query_inputs.append(text)
        return [1.0]

    def get_text_embedding_batch(self, texts: list[str], **_kwargs) -> list[list[float]]:
        self.document_inputs.extend(texts)
        return [[1.0] for _ in texts]


class _SingleResultStore:
    """Minimal injected store that returns one unit-norm dense result."""

    cache_identity = "query-preparation-test-store"

    def count(self, _collection_name: str) -> int:
        return 1

    def query_dense(self, **_kwargs) -> list[dict]:
        return [
            {
                "id": "chunk-1",
                "score": 1.0,
                "score_kind": "dense_similarity_v1",
                "document": "stored evidence",
                "metadata": {"file_path": "evidence.md"},
            }
        ]

    def close(self) -> None:
        return None


def _settings(
    instruction: str = INSTRUCTION,
    *,
    hybrid_enabled: bool = False,
) -> EffectiveSettings:
    """Build injected settings for one query-preparation scenario."""
    return EffectiveSettings(
        embedding=EmbeddingBlock(query_instruction=instruction),
        retrieval=RetrievalBlock(hybrid_enabled=hybrid_enabled),
        metadata=MetadataBlock(extraction_mode="disabled"),
    )


def test_embedding_query_instruction_has_empty_default_and_nested_env_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 4.1: settings expose EMBEDDING__QUERY_INSTRUCTION."""
    from pydantic import ValidationError

    from omrg.compose import settings_to_effective
    from omrg.config import Settings

    monkeypatch.delenv("EMBEDDING__QUERY_INSTRUCTION", raising=False)
    assert Settings().embedding.query_instruction == ""

    monkeypatch.setenv("EMBEDDING__QUERY_INSTRUCTION", INSTRUCTION)
    configured = Settings(pdf_reader="pypdf")
    assert configured.embedding.query_instruction == INSTRUCTION
    effective = settings_to_effective(configured)
    assert effective.embedding.query_instruction == INSTRUCTION
    with pytest.raises(ValidationError):
        effective.embedding.query_instruction = "mutated"


def test_dense_query_embedding_uses_exact_prepared_text_and_cache_key(monkeypatch) -> None:
    """Tasks 4.2 and 4.4: dense receives the exact prepared query once."""
    from omrg.core.retrieval.pipeline import search

    embedder = _RecordingEmbedding("dense-test-model")
    cache: OrderedDict = OrderedDict()
    monkeypatch.setattr("omrg.core.retrieval.pipeline.assemble", lambda results, **_kwargs: results)

    search(
        RAW_QUERY,
        collection_name="documents",
        rerank=False,
        store=cast(Any, _SingleResultStore()),
        effective_settings=_settings(),
        embed_model=embedder,
        query_cache=cache,
    )

    assert embedder.query_inputs == [PREPARED_QUERY]
    assert (PREPARED_QUERY, "dense-test-model") in cache


def test_empty_instruction_preserves_the_raw_query(monkeypatch) -> None:
    """Task 4.3: empty configuration must not add formatting bytes."""
    from omrg.core.retrieval.pipeline import search

    embedder = _RecordingEmbedding("empty-instruction-model")
    monkeypatch.setattr("omrg.core.retrieval.pipeline.assemble", lambda results, **_kwargs: results)

    search(
        RAW_QUERY,
        collection_name="documents",
        rerank=False,
        store=cast(Any, _SingleResultStore()),
        effective_settings=_settings(""),
        embed_model=embedder,
        query_cache=OrderedDict(),
    )

    assert embedder.query_inputs == [RAW_QUERY]


def test_instruction_change_uses_a_distinct_prepared_query_cache_entry(monkeypatch) -> None:
    """Tasks 4.5-4.6: prepared cache entries separate and then reuse."""
    from omrg.core.retrieval.pipeline import search

    embedder = _RecordingEmbedding("instruction-change-model")
    cache: OrderedDict = OrderedDict()
    monkeypatch.setattr("omrg.core.retrieval.pipeline.assemble", lambda results, **_kwargs: results)

    search(
        RAW_QUERY,
        collection_name="documents",
        rerank=False,
        store=cast(Any, _SingleResultStore()),
        effective_settings=_settings(""),
        embed_model=embedder,
        query_cache=cache,
    )
    search(
        RAW_QUERY,
        collection_name="documents",
        rerank=False,
        store=cast(Any, _SingleResultStore()),
        effective_settings=_settings(),
        embed_model=embedder,
        query_cache=cache,
    )
    search(
        RAW_QUERY,
        collection_name="documents",
        metadata_filter={"category": "proof"},
        rerank=False,
        store=cast(Any, _SingleResultStore()),
        effective_settings=_settings(),
        embed_model=embedder,
        query_cache=cache,
    )

    assert embedder.query_inputs == [RAW_QUERY, PREPARED_QUERY]
    assert set(cache) == {
        (RAW_QUERY, "instruction-change-model"),
        (PREPARED_QUERY, "instruction-change-model"),
    }


def test_document_embedding_text_never_uses_the_query_instruction() -> None:
    """Task 4.3: document embedding remains separate from query preparation."""
    from omrg.core.ingestion.replacement import _embed_missing_nodes
    from omrg.core.settings import EmbeddingBlock

    embedder = _RecordingEmbedding("document-test-model")
    node = TextNode(text="Document evidence", metadata={"category": "proof"})
    expected = node.get_content(metadata_mode=MetadataMode.EMBED)
    configured = EmbeddingBlock(query_instruction=INSTRUCTION)

    _embed_missing_nodes([node], embed_model=embedder)

    assert configured.query_instruction == INSTRUCTION
    assert embedder.document_inputs == [expected]
    assert PREPARED_QUERY not in embedder.document_inputs[0]


def test_hybrid_dense_uses_prepared_query_while_sparse_and_reranker_stay_raw(monkeypatch) -> None:
    """Task 4.6: preparation applies only to the dense embedding call."""
    import omrg.core.retrieval.pipeline as pipeline

    sparse_inputs: list[str] = []
    reranker_inputs: list[str] = []

    def sparse_runner(_collection, _store, query, _fetch_k, *_args, **_kwargs):
        sparse_inputs.append(query)
        return []

    class _Reranker:
        def rerank(self, query, results, *, top_k):
            reranker_inputs.append(query)
            return [dict(result, _reranked=True) for result in results[:top_k]]

    monkeypatch.setattr(pipeline, "_sparse_bm25_query", sparse_runner)
    monkeypatch.setattr(pipeline, "assemble", lambda results, **_kwargs: results)

    embedder = _RecordingEmbedding("hybrid-model")
    pipeline.search(
        RAW_QUERY,
        collection_name="documents",
        hybrid=True,
        rerank=True,
        reranker=_Reranker(),
        store=cast(Any, _SingleResultStore()),
        effective_settings=_settings(hybrid_enabled=True),
        embed_model=embedder,
        query_cache=OrderedDict(),
    )

    assert embedder.query_inputs == [PREPARED_QUERY]
    assert sparse_inputs == [RAW_QUERY]
    assert reranker_inputs == [RAW_QUERY]


def test_each_engine_owns_its_prepared_query_cache_and_close_clears_only_its_cache(
    monkeypatch,
) -> None:
    """Tasks 4.4 and 4.7: engine cache lifecycle remains isolated."""
    from omrg.engine import Engine

    monkeypatch.setattr("omrg.core.retrieval.pipeline.assemble", lambda results, **_kwargs: results)
    embedder_a = _RecordingEmbedding("engine-model")
    embedder_b = _RecordingEmbedding("engine-model")
    engine_a = Engine(
        _settings(),
        store=cast(Any, _SingleResultStore()),
        embed_model=cast(Any, embedder_a),
    )
    engine_b = Engine(
        _settings(),
        store=cast(Any, _SingleResultStore()),
        embed_model=cast(Any, embedder_b),
    )

    engine_a.search(RAW_QUERY, rerank=False)
    engine_b.search(RAW_QUERY, rerank=False)

    assert embedder_a.query_inputs == [PREPARED_QUERY]
    assert embedder_b.query_inputs == [PREPARED_QUERY]
    assert engine_a._query_cache is not engine_b._query_cache
    assert engine_a._query_cache
    assert engine_b._query_cache

    engine_a.close()

    assert not engine_a._query_cache
    assert engine_b._query_cache
    engine_b.close()


def test_query_instruction_does_not_change_source_index_identity() -> None:
    """Task 4.8: query-only configuration keeps unchanged source detection valid."""
    from omrg.core.ingestion.source_state import build_index_identity

    baseline = build_index_identity(
        _settings(""), content_type="text/markdown", chunk_size=512, chunk_overlap=100
    )
    instructed_settings = _settings()
    assert instructed_settings.embedding.query_instruction == INSTRUCTION
    instructed = build_index_identity(
        instructed_settings, content_type="text/markdown", chunk_size=512, chunk_overlap=100
    )

    assert instructed == baseline


@pytest.mark.asyncio
async def test_query_instruction_change_keeps_unchanged_source_skipped(sample_md, tmp_path) -> None:
    """Task 4.8: query-only configuration must not trigger a re-index."""
    from llama_index.core import Settings as LlamaIndexSettings

    from omrg.core.ingestion.pipeline import ingest_path_async
    from omrg.core.vectordb.lancedb import LanceVectorStore

    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    embedder = LlamaIndexSettings.embed_model
    raw_settings = _settings("")
    instructed_settings = _settings()

    assert instructed_settings.embedding.query_instruction == INSTRUCTION
    first = await ingest_path_async(
        str(sample_md),
        collection_name="documents",
        effective_settings=raw_settings,
        store=store,
        embed_model=embedder,
    )
    second = await ingest_path_async(
        str(sample_md),
        collection_name="documents",
        effective_settings=instructed_settings,
        store=store,
        embed_model=embedder,
    )

    assert first["files_indexed"] == 1
    assert second["files_indexed"] == 0
    assert second["files_skipped_unchanged"] == 1
    assert second["file_details"][0]["status"] == "skipped_unchanged"
    store.close()
