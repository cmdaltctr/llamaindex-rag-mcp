"""Clean-boundary regression for pre-lineage production rows (task 1.9).

Supersedes the Stage 3A legacy auto-migration regression: rows for a canonical
``file_path`` that lack or disagree on ``source_id`` must fail ingestion
BEFORE parsing, embedding, or store mutation, keep the stored rows unchanged,
and tell the operator to rebuild. Unrelated experiment-style collections are
never scanned at startup or during the failed ingestion.

The chroma/lancedb parametrisation follows ``tests/test_ingestion_stage3.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from llama_index.core import Settings
from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode

from omrg.core.ingestion import ingest_path_async, pipeline
from omrg.core.vectordb import get_default_store, set_default_store
from omrg.core.vectordb.identity import EmbeddingIdentity
from omrg.core.vectordb.lancedb import LanceVectorStore

_COLLECTION = "stage3_legacy"
_EXPERIMENT_COLLECTION = "stage3_legacy_experiment_only"
_EMBED_DIM = 384  # the conftest MockEmbedding dimension


@pytest.fixture(params=["chroma", "lancedb"])
def legacy_store(request: pytest.FixtureRequest, tmp_path: Path):
    """Install one real store implementation behind the process default."""
    if request.param == "chroma":
        return get_default_store()
    store = LanceVectorStore(uri=str(tmp_path / "legacy-lancedb"))
    set_default_store(store)
    return store


def _seed_node(
    store, source: Path, *, source_id: str | None, text: str = "legacy searchable sentinel"
) -> None:
    """Write one production-shaped row, optionally carrying a source_id."""
    metadata: dict = {"file_path": str(source)}
    if source_id is not None:
        metadata["source_id"] = source_id
    # Real pipeline rows always set the SOURCE relationship. Without it the
    # LanceDB adapter types the top-level doc_id column as Null, and no later
    # pipeline write can cast its Utf8 doc_id into that column.
    store.write_nodes(
        [
            TextNode(
                text=text,
                metadata=metadata,
                relationships={
                    NodeRelationship.SOURCE: RelatedNodeInfo(
                        node_id="00000000-0000-0000-0000-000000000000"
                    )
                },
            )
        ],
        _COLLECTION,
    )


def _forbid_post_guard_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make parsing and embedding fail loudly if the guard ever runs late."""

    async def forbid_parse(*args, **kwargs):
        raise AssertionError("incompatible lineage must be detected before parsing")

    def forbid_embedding(*args, **kwargs):
        raise AssertionError("incompatible lineage must be detected before embedding")

    monkeypatch.setattr(pipeline, "read_and_chunk_file_async", forbid_parse)
    # MockEmbedding is a pydantic model, so the method is patched on the
    # class: instance-level attribute assignment is rejected by pydantic.
    monkeypatch.setattr(type(Settings.embed_model), "get_text_embedding_batch", forbid_embedding)


def _seed_experiment_rows(store) -> tuple[int, int]:
    """Seed a precomputed-style collection with no production file_path."""
    store.upsert_precomputed(
        _EXPERIMENT_COLLECTION,
        ids=["exp-1"],
        documents=["experiment sentinel"],
        metadatas=[{"experiment": "demo"}],
        embeddings=[[0.1] * _EMBED_DIM],
        embedding_identity=EmbeddingIdentity(provider="test-provider", model="test-model"),
    )
    return store.count(_EXPERIMENT_COLLECTION), store.get_generation(_EXPERIMENT_COLLECTION)


@pytest.mark.asyncio
async def test_pre_lineage_rows_fail_before_mutation_with_rebuild_instruction(
    tmp_path: Path,
    legacy_store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec: rows without source identity reject ingestion and stay unchanged."""
    source = tmp_path / "legacy.txt"
    source.write_text("current source content " * 80, encoding="utf-8")
    _seed_node(legacy_store, source, source_id=None)
    generation_before = legacy_store.get_generation(_COLLECTION)
    _forbid_post_guard_stages(monkeypatch)

    result = await ingest_path_async(str(source), collection_name=_COLLECTION)

    assert result["status"] == "error"
    detail = result["file_details"][0]
    assert detail["status"] == "failed"
    assert "rebuild" in detail["error"].lower()

    assert legacy_store.get_generation(_COLLECTION) == generation_before
    rows = [
        row
        for row in legacy_store.iter_documents(_COLLECTION)
        if row[2].get("file_path") == str(source)
    ]
    assert len(rows) == 1
    assert "legacy searchable sentinel" in rows[0][1]


@pytest.mark.asyncio
async def test_disagreeing_source_id_fails_before_mutation(
    tmp_path: Path,
    legacy_store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec: rows carrying a different source_id fail the same way."""
    source = tmp_path / "disagreeing.txt"
    source.write_text("current source content " * 80, encoding="utf-8")
    _seed_node(legacy_store, source, source_id="src_" + "f" * 64)
    generation_before = legacy_store.get_generation(_COLLECTION)
    _forbid_post_guard_stages(monkeypatch)

    result = await ingest_path_async(str(source), collection_name=_COLLECTION)

    assert result["status"] == "error"
    detail = result["file_details"][0]
    assert detail["status"] == "failed"
    assert "rebuild" in detail["error"].lower()

    assert legacy_store.get_generation(_COLLECTION) == generation_before
    rows = [
        row
        for row in legacy_store.iter_documents(_COLLECTION)
        if row[2].get("file_path") == str(source)
    ]
    assert len(rows) == 1
    assert rows[0][2].get("source_id") == "src_" + "f" * 64


@pytest.mark.asyncio
async def test_unrelated_precomputed_collection_is_not_scanned(
    tmp_path: Path,
    legacy_store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec: no startup scan or migration touches experiment-only rows."""
    experiment_count, experiment_generation = _seed_experiment_rows(legacy_store)
    source = tmp_path / "legacy-with-experiments.txt"
    source.write_text("current source content " * 80, encoding="utf-8")
    _seed_node(legacy_store, source, source_id=None)
    _forbid_post_guard_stages(monkeypatch)

    result = await ingest_path_async(str(source), collection_name=_COLLECTION)

    assert result["status"] == "error"
    assert legacy_store.count(_EXPERIMENT_COLLECTION) == experiment_count
    assert legacy_store.get_generation(_EXPERIMENT_COLLECTION) == experiment_generation
    # The failing production source itself is untouched too.
    rows = [
        row
        for row in legacy_store.iter_documents(_COLLECTION)
        if row[2].get("file_path") == str(source)
    ]
    assert len(rows) == 1
