"""Legacy-row migration regression for Stage 3A replacement semantics."""

from __future__ import annotations

from pathlib import Path

import pytest
from llama_index.core.schema import (
    NodeRelationship,
    RelatedNodeInfo,
    TextNode,
)

from rag_mcp.core.ingestion import ingest_path_async
from rag_mcp.core.vectordb import get_default_store, set_default_store
from rag_mcp.core.vectordb.lancedb import LanceVectorStore

_COLLECTION = "stage3_legacy"


@pytest.fixture(params=["chroma", "lancedb"])
def legacy_store(request: pytest.FixtureRequest, tmp_path: Path):
    """Install one real store implementation behind the process default."""
    if request.param == "chroma":
        return get_default_store()
    store = LanceVectorStore(uri=str(tmp_path / "legacy-lancedb"))
    set_default_store(store)
    return store


def _source_rows(store, source: Path) -> list[tuple[str, str, dict]]:
    """Return all rows whose user metadata points at *source*."""
    return [
        row for row in store.iter_documents(_COLLECTION) if row[2].get("file_path") == str(source)
    ]


@pytest.mark.asyncio
async def test_legacy_row_without_attempt_is_replaced_by_id_once(
    tmp_path: Path,
    legacy_store,
) -> None:
    """Pre-Stage-3 rows are stale even when ``source_attempt`` is absent.

    The successful replacement performs exactly two store mutations after the
    legacy seed: one candidate write and one stale-ID delete. This also pins
    the store-owned generation contract for the new ``delete_ids`` operation.
    """
    source = tmp_path / "legacy.txt"
    source.write_text("current source content " * 80, encoding="utf-8")

    # Real pre-Stage-3 rows were written by the pipeline, which always sets
    # the SOURCE relationship. Without it the LanceDB adapter types the
    # top-level doc_id column as Null, and no later pipeline write can cast
    # its Utf8 doc_id into that column.
    legacy_node = TextNode(
        text="legacy searchable sentinel",
        metadata={"file_path": str(source)},
        relationships={
            NodeRelationship.SOURCE: RelatedNodeInfo(node_id="00000000-0000-0000-0000-000000000000")
        },
    )
    legacy_store.write_nodes(
        [legacy_node],
        _COLLECTION,
    )
    generation_before = legacy_store.get_generation(_COLLECTION)
    assert generation_before == 1

    result = await ingest_path_async(str(source), collection_name=_COLLECTION)

    assert result["status"] == "ok"
    assert result["files_indexed"] == 1
    assert result["files_skipped_unchanged"] == 0
    assert result["chunks_removed"] == 1
    assert legacy_store.get_generation(_COLLECTION) == generation_before + 2

    rows = _source_rows(legacy_store, source)
    assert rows
    assert all("legacy searchable sentinel" not in text for _, text, _ in rows)
    assert any("current source content" in text for _, text, _ in rows)
    assert all(metadata.get("source_attempt") for _, _, metadata in rows)
