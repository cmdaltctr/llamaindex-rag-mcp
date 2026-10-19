"""One Engine routes embedding models by collection profile (ADR-081, D5, D6)."""

from __future__ import annotations

import asyncio
from typing import Any

from tests.unit.test_engine_pipelines_support import (
    Factory,
    FakeEmbedder,
    FakeLLM,
    FakeResolver,
    FakeStore,
    build_engine,
    chunks,
)

from omrg.core.vectordb.identity import EmbeddingIdentity
from omrg.engine_embedders import EngineEmbedders

HOST = EmbeddingIdentity(provider="ollama", model="model-a")
CHOICE_B = EmbeddingIdentity(provider="llamacpp", model="model-b")


class _RecordingEmbedder(FakeEmbedder):
    def __init__(self, model_name: str) -> None:
        super().__init__(model_name)
        self.queries: list[str] = []

    def get_query_embedding(self, query: str) -> list[float]:
        self.queries.append(query)
        return super().get_query_embedding(query)


class _IdentityStore(FakeStore):
    """FakeStore that records the identity each dense query and write supplies."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        super().__init__(rows, metadata={"papers": {}, "notes": {}})
        self.query_identities: list[EmbeddingIdentity | None] = []

    def query_dense(
        self, collection_name, query_embedding, n_results, where=None, *, embedding_identity=None
    ):  # noqa: ANN001, ANN201
        self.query_identities.append(embedding_identity)
        return super().query_dense(collection_name, query_embedding, n_results, where)


class _ChoiceResolver(FakeResolver):
    """Resolver whose ``papers`` collection follows a profile that names model B."""

    def embedding_choice(self, collection: str) -> EmbeddingIdentity | None:
        return CHOICE_B if collection == "papers" else None


def _engine(effective_settings, **kwargs: Any):  # noqa: ANN202
    settings = effective_settings(hybrid_enabled=False, rerank_enabled=False)
    host = _RecordingEmbedder("model-a")
    built: list[_RecordingEmbedder] = []

    def factory(provider: str, model: str) -> _RecordingEmbedder:
        embedder = _RecordingEmbedder(model)
        built.append(embedder)
        return embedder

    store = _IdentityStore(chunks())
    engine = build_engine(
        settings,
        store,
        embed_model=host,
        embedders=EngineEmbedders(host, HOST, factory),
        profile_resolver=_ChoiceResolver({"papers": settings, "notes": settings}),
        **kwargs,
    )
    return engine, host, built, store


def test_search_embeds_a_profile_collection_with_its_own_model(effective_settings) -> None:
    engine, host, built, store = _engine(effective_settings)

    engine.search("what proves it", collection_name="papers", rerank=False)

    assert [e.model_name for e in built] == ["model-b"]
    assert built[0].queries and not host.queries
    assert store.query_identities == [CHOICE_B]


def test_collection_without_a_choice_uses_the_host_model(effective_settings) -> None:
    engine, host, built, store = _engine(effective_settings)

    engine.search("what proves it", collection_name="notes", rerank=False)

    assert host.queries and built == []
    assert store.query_identities == [None]


def test_answer_retrieves_with_the_profile_model(effective_settings) -> None:
    engine, host, built, store = _engine(effective_settings, answer_llm_factory=Factory(FakeLLM()))

    asyncio.run(engine.answer("what proves it", collection_name="papers"))

    assert built and built[0].queries and not host.queries
    assert store.query_identities[0] == CHOICE_B


def test_ingest_writes_with_the_profile_identity(effective_settings, monkeypatch, tmp_path) -> None:
    engine, host, built, store = _engine(effective_settings)
    seen: dict[str, Any] = {}

    async def fake_ingest(path: str, **kwargs: Any) -> dict:
        seen.update(kwargs)
        return {"status": "ok"}

    monkeypatch.setattr("omrg.core.ingestion.pipeline.ingest_path_async", fake_ingest)
    asyncio.run(engine.ingest(str(tmp_path), collection_name="papers"))

    assert seen["embed_model"] is built[0]
    assert seen["embedding_identity"] == CHOICE_B


def test_two_engines_with_the_same_choice_use_different_instances(effective_settings) -> None:
    first, _, first_built, _ = _engine(effective_settings)
    second, _, second_built, _ = _engine(effective_settings)

    first.search("q", collection_name="papers", rerank=False)
    second.search("q", collection_name="papers", rerank=False)

    assert first_built[0] is not second_built[0]


def test_closing_one_engine_leaves_the_other_working(effective_settings) -> None:
    first, _, _, _ = _engine(effective_settings)
    second, _, second_built, _ = _engine(effective_settings)
    second.search("q", collection_name="papers", rerank=False)

    first.close()
    second.search("q again", collection_name="papers", rerank=False)

    assert second_built[0].queries == ["q", "q again"]
