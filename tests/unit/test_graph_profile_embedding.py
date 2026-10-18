"""Graph runs use the embedding model of the collection's profile (ADR-081, D6, 6.7)."""

from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Any

import pytest
from llama_index.core.embeddings import MockEmbedding
from tests.fixtures.pipeline_parity.ingestion.snapshot import copy_sources, pin_detection
from tests.unit.test_engine_pipelines_support import (
    FakeEmbedder,
    FakeResolver,
    FakeStore,
    build_engine,
    chunks,
    identity_metadata,
    retrieval_graph,
)
from tests.unit.test_ingestion_graph_adapters_support import offline_settings

from omrg.core.pipelines import PipelineValidationError, RunStatus
from omrg.core.vectordb.identity import EmbeddingIdentity
from omrg.core.vectordb.lancedb.store import LanceVectorStore
from omrg.engine_embedders import EngineEmbedders

HOST = EmbeddingIdentity(provider="ollama", model="model-a")
CHOICE_B = EmbeddingIdentity(provider="llamacpp", model="model-b")


class _Embedder(FakeEmbedder):
    def __init__(self, model_name: str) -> None:
        super().__init__(model_name)
        self.queries: list[str] = []

    def get_query_embedding(self, query: str) -> list[float]:
        self.queries.append(query)
        return super().get_query_embedding(query)


class _UnitEmbedding(MockEmbedding):
    def _get_vector(self) -> list[float]:
        vector = super()._get_vector()
        norm = math.sqrt(math.fsum(x * x for x in vector))
        return [x / norm for x in vector]


class _ChoiceResolver(FakeResolver):
    def embedding_choice(self, collection: str) -> EmbeddingIdentity | None:
        return CHOICE_B if collection == "papers" else None


class _RecordingStore(FakeStore):
    def __init__(self, rows: list[dict[str, Any]], **kwargs: Any) -> None:
        super().__init__(rows, **kwargs)
        self.query_identities: list[EmbeddingIdentity | None] = []

    def query_dense(
        self, collection_name, query_embedding, n_results, where=None, *, embedding_identity=None
    ):  # noqa: ANN001, ANN201
        self.query_identities.append(embedding_identity)
        return super().query_dense(collection_name, query_embedding, n_results, where)


def _engine(effective_settings, store: Any, embedders: EngineEmbedders):  # noqa: ANN202
    settings = effective_settings(hybrid_enabled=False, rerank_enabled=False)
    resolver = _ChoiceResolver({"papers": settings, "notes": settings})
    return build_engine(settings, store, embedders=embedders, profile_resolver=resolver)


def _embedders(built: list[_Embedder]) -> EngineEmbedders:
    def factory(provider: str, model: str) -> _Embedder:
        built.append(_Embedder(model))
        return built[-1]

    return EngineEmbedders(_Embedder("model-a"), HOST, factory)


def _validate(engine: Any, collection: str) -> Any:
    return engine.validate_pipeline(retrieval_graph(), inputs={"query": "q"}, collection=collection)


def test_preflight_accepts_a_collection_stamped_with_the_profile_model(effective_settings) -> None:
    meta = {"papers": identity_metadata("llamacpp", "model-b")}
    store = _RecordingStore(chunks(), metadata=meta, identity=HOST)
    engine = _engine(effective_settings, store, _embedders([]))

    _validate(engine, "papers")


def test_preflight_refuses_a_collection_stamped_with_another_model(effective_settings) -> None:
    meta = {"papers": identity_metadata("ollama", "model-a")}
    store = _RecordingStore(chunks(), metadata=meta, identity=HOST)
    engine = _engine(effective_settings, store, _embedders([]))

    with pytest.raises(PipelineValidationError) as caught:
        _validate(engine, "papers")

    assert "embedding_identity_mismatch" in caught.value.codes
    message = str(caught.value.issues[0].message)
    assert "ollama/model-a" in message and "llamacpp/model-b" in message


def test_preflight_still_accepts_the_host_model_for_a_plain_collection(effective_settings) -> None:
    meta = {"notes": identity_metadata("ollama", "model-a")}
    store = _RecordingStore(chunks(), metadata=meta, identity=HOST)
    engine = _engine(effective_settings, store, _embedders([]))

    _validate(engine, "notes")


def test_dense_step_embeds_with_the_profile_model_and_sends_its_identity(
    effective_settings,
) -> None:
    meta = {"papers": identity_metadata("llamacpp", "model-b")}
    store = _RecordingStore(chunks(), metadata=meta, identity=HOST)
    built: list[_Embedder] = []
    engine = _engine(effective_settings, store, _embedders(built))
    graph = retrieval_graph()
    graph["collection"] = "papers"

    result = asyncio.run(engine.run_pipeline(graph, inputs={"query": "what proves it"}))

    assert result.status is RunStatus.SUCCEEDED
    assert built and built[0].queries
    assert store.query_identities == [CHOICE_B]


def test_sparse_step_sends_the_profile_identity_to_the_native_backend(
    effective_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrg.core.retrieval import sparse_dispatch

    seen: list[EmbeddingIdentity | None] = []

    def native(*args: Any, embedding_identity: Any = None, **kwargs: Any) -> list[dict]:
        seen.append(embedding_identity)
        return []

    monkeypatch.setattr(sparse_dispatch, "_native_sparse_query", native)
    meta = {"papers": identity_metadata("llamacpp", "model-b")}
    store = _RecordingStore(chunks(), metadata=meta, identity=HOST)
    settings = effective_settings(
        hybrid_enabled=False, rerank_enabled=False, hybrid_sparse_backend="native"
    )
    resolver = _ChoiceResolver({"papers": settings})
    engine = build_engine(settings, store, embedders=_embedders([]), profile_resolver=resolver)
    graph = retrieval_graph()
    graph["collection"] = "papers"
    graph["nodes"] = [
        {"id": "prepare", "operation": "retrieve.prepare_query", "params": {}},
        {"id": "sparse", "operation": "retrieve.sparse"},
        {"id": "fuse", "operation": "combine.rrf"},
        {"id": "context", "operation": "context.assemble"},
    ]
    graph["edges"] = [
        {"source": {"node": a, "port": b}, "target": {"node": c, "port": d}}
        for a, b, c, d in [
            ("prepare", "query", "sparse", "query"),
            ("sparse", "evidence", "fuse", "ranked"),
            ("fuse", "evidence", "context", "evidence"),
        ]
    ]

    asyncio.run(engine.run_pipeline(graph, inputs={"query": "what proves it"}))

    assert seen == [CHOICE_B]


def test_commit_step_writes_and_stamps_the_profile_identity(
    effective_settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from omrg.pipeline_templates import canonical_templates

    pin_detection(monkeypatch)
    root = copy_sources(tmp_path)
    settings = offline_settings(effective_settings)
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"), embedding_identity=HOST)
    embedders = EngineEmbedders(
        _UnitEmbedding(embed_dim=8, model_name="model-a"),
        HOST,
        lambda provider, model: _UnitEmbedding(embed_dim=8, model_name=model),
    )
    engine = build_engine(
        settings,
        store,
        embedders=embedders,
        profile_resolver=_ChoiceResolver({"papers": settings}),
    )
    ingestion = canonical_templates("papers", hybrid=False, rerank=False)[0].definition

    result = asyncio.run(engine.run_pipeline(ingestion, inputs={"path": str(root)}))

    assert result.status is RunStatus.SUCCEEDED
    stamp = store.get_collection_metadata("papers") or {}
    assert (stamp["rag_embed_provider"], stamp["rag_embed_model"]) == ("llamacpp", "model-b")
