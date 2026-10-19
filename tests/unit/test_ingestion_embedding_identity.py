"""Ingestion writes with the embedding identity it is given (ADR-081)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
from llama_index.core.embeddings import MockEmbedding

from omrg.core.ingestion import ingest_path_async
from omrg.core.vectordb.identity import EmbeddingIdentity
from omrg.core.vectordb.lancedb.store import LanceVectorStore

IDENTITY_A = EmbeddingIdentity(provider="ollama", model="model-a")
IDENTITY_B = EmbeddingIdentity(provider="ollama", model="model-b")


class _UnitEmbedding(MockEmbedding):
    """MockEmbedding with unit-norm vectors, so the norm guard accepts it."""

    def _get_vector(self) -> list[float]:
        vector = super()._get_vector()
        norm = math.sqrt(math.fsum(x * x for x in vector))
        return [x / norm for x in vector] if norm else list(vector)


class _RecordingStore(LanceVectorStore):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.write_identities: list[EmbeddingIdentity | None] = []

    def write_nodes(self, nodes, collection_name, **kwargs):  # noqa: ANN001, ANN003, ANN201
        self.write_identities.append(kwargs.get("embedding_identity"))
        return super().write_nodes(nodes, collection_name, **kwargs)


@pytest.mark.asyncio
async def test_ingest_reaches_write_nodes_with_the_supplied_identity(
    sample_md: Path, tmp_path: Path, effective_settings
) -> None:
    store = _RecordingStore(uri=str(tmp_path / "lancedb"), embedding_identity=IDENTITY_A)
    await ingest_path_async(
        str(sample_md),
        collection_name="papers",
        store=store,
        embed_model=_UnitEmbedding(embed_dim=8, model_name="model-b"),
        effective_settings=effective_settings(),
        embedding_identity=IDENTITY_B,
    )

    assert store.write_identities == [IDENTITY_B]
    stamp = store.get_collection_metadata("papers") or {}
    assert stamp["rag_embed_model"] == "model-b"


@pytest.mark.asyncio
async def test_ingest_without_identity_keeps_the_composed_identity(
    sample_md: Path, tmp_path: Path, effective_settings
) -> None:
    store = _RecordingStore(uri=str(tmp_path / "lancedb"), embedding_identity=IDENTITY_A)
    await ingest_path_async(
        str(sample_md),
        collection_name="papers",
        store=store,
        embed_model=_UnitEmbedding(embed_dim=8, model_name="model-a"),
        effective_settings=effective_settings(),
    )

    assert store.write_identities == [None]
    assert (store.get_collection_metadata("papers") or {})["rag_embed_model"] == "model-a"
