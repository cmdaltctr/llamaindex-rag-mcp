"""Stage 3A regressions for bounded, failure-safe ingestion.

These tests are deterministic and use only the suite's mock embedding model plus
local ephemeral vector stores. They do not run calibration experiments.
"""

from __future__ import annotations

import asyncio
import gc
import weakref
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag_mcp.core.ingestion import ingest_path_async
from rag_mcp.core.ingestion.metrics import sample_peak_rss_bytes
from rag_mcp.core.settings import EffectiveSettings, MetadataBlock
from rag_mcp.core.vectordb import get_default_store, set_default_store
from rag_mcp.core.vectordb.lancedb import LanceVectorStore

_COLLECTION = "stage3_ingestion"


@pytest.fixture(params=["chroma", "lancedb"])
def stage3_store(request: pytest.FixtureRequest, tmp_path: Path):
    """Install one real store implementation behind the process default."""
    if request.param == "chroma":
        return get_default_store()
    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    set_default_store(store)
    return store


def _source_texts(store, source: Path) -> list[str]:
    """Return every stored text row for one source path."""
    return [
        text
        for _, text, metadata in store.iter_documents(_COLLECTION)
        if metadata.get("file_path") == str(source)
    ]


@pytest.mark.asyncio
async def test_repeated_ingest_skips_complete_matching_version(
    tmp_path: Path,
    stage3_store,
) -> None:
    """Same bytes and same index identity skip parse/embed/write on both stores."""
    source = tmp_path / "same.txt"
    source.write_text("same source content " * 80, encoding="utf-8")

    first = await ingest_path_async(str(source), collection_name=_COLLECTION)
    second = await ingest_path_async(str(source), collection_name=_COLLECTION)

    assert first["status"] == "ok"
    assert first["files_indexed"] == 1
    assert first["chunks_created"] > 0
    assert second["status"] == "ok"
    assert second["files_indexed"] == 0
    assert second["files_skipped_unchanged"] == 1
    assert second["chunks_created"] == 0
    assert second["chunks_removed"] == 0
    assert stage3_store.count(_COLLECTION) == first["chunks_created"]


@pytest.mark.asyncio
async def test_content_edit_replaces_only_old_source_version(
    tmp_path: Path,
    stage3_store,
) -> None:
    """Changed source bytes reprocess and remove the previous verified rows."""
    source = tmp_path / "edited.txt"
    source.write_text("version alpha " * 100, encoding="utf-8")
    first = await ingest_path_async(str(source), collection_name=_COLLECTION)

    source.write_text("version beta changed " * 130, encoding="utf-8")
    second = await ingest_path_async(str(source), collection_name=_COLLECTION)

    assert second["status"] == "ok"
    assert second["files_indexed"] == 1
    assert second["files_skipped_unchanged"] == 0
    assert second["chunks_removed"] == first["chunks_created"]
    texts = _source_texts(stage3_store, source)
    assert texts
    assert all("version alpha" not in text for text in texts)
    assert any("version beta changed" in text for text in texts)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first_settings", "second_settings"),
    [
        (
            EffectiveSettings(
                metadata=MetadataBlock(extraction_mode="disabled"),
                embed_provider="ollama",
                embed_model="stage3-model-a",
            ),
            EffectiveSettings(
                metadata=MetadataBlock(extraction_mode="disabled"),
                embed_provider="ollama",
                embed_model="stage3-model-b",
            ),
        ),
        (
            EffectiveSettings(
                metadata=MetadataBlock(extraction_mode="disabled"),
                pdf_reader="pypdf",
            ),
            EffectiveSettings(
                metadata=MetadataBlock(extraction_mode="disabled"),
                pdf_reader="liteparse",
            ),
        ),
    ],
    ids=["embedding-model-change", "parser-selector-change"],
)
async def test_index_identity_change_forces_reprocessing(
    tmp_path: Path,
    stage3_store,
    first_settings: EffectiveSettings,
    second_settings: EffectiveSettings,
) -> None:
    """Embedding or parser-selector changes invalidate unchanged-file skips."""
    source = tmp_path / "identity.txt"
    source.write_text("identity-sensitive content " * 100, encoding="utf-8")

    first = await ingest_path_async(
        str(source),
        collection_name=_COLLECTION,
        effective_settings=first_settings,
    )
    second = await ingest_path_async(
        str(source),
        collection_name=_COLLECTION,
        effective_settings=second_settings,
    )

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second["files_indexed"] == 1
    assert second["files_skipped_unchanged"] == 0
    assert second["chunks_removed"] == first["chunks_created"]


@pytest.mark.asyncio
async def test_chunk_setting_change_forces_reprocessing(
    tmp_path: Path,
    stage3_store,
) -> None:
    """Per-call chunk-shaping overrides participate in source index identity."""
    source = tmp_path / "chunked.txt"
    source.write_text("chunk boundary sensitive text " * 250, encoding="utf-8")

    first = await ingest_path_async(
        str(source),
        chunk_size=256,
        chunk_overlap=32,
        collection_name=_COLLECTION,
    )
    second = await ingest_path_async(
        str(source),
        chunk_size=96,
        chunk_overlap=12,
        collection_name=_COLLECTION,
    )

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second["files_indexed"] == 1
    assert second["files_skipped_unchanged"] == 0
    assert second["chunks_removed"] == first["chunks_created"]


@pytest.mark.asyncio
async def test_parse_failure_preserves_last_searchable_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A replacement parse failure does not delete the durable old source."""
    from rag_mcp.core.ingestion import pipeline

    store = get_default_store()
    source = tmp_path / "parse-failure.txt"
    source.write_text("old parse sentinel " * 80, encoding="utf-8")
    first = await ingest_path_async(str(source), collection_name=_COLLECTION)
    assert first["status"] == "ok"

    source.write_text("new parse sentinel " * 90, encoding="utf-8")

    async def fail_parse(*args, **kwargs):
        raise ValueError("injected parse failure")

    monkeypatch.setattr(pipeline, "read_and_chunk_file_async", fail_parse)
    failed = await ingest_path_async(str(source), collection_name=_COLLECTION)

    assert failed["status"] == "error"
    texts = _source_texts(store, source)
    assert any("old parse sentinel" in text for text in texts)
    assert all("new parse sentinel" not in text for text in texts)


@pytest.mark.asyncio
async def test_embedding_failure_preserves_last_searchable_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A replacement embedding failure leaves the old source searchable."""
    from rag_mcp.core.ingestion import replacement

    store = get_default_store()
    source = tmp_path / "embed-failure.txt"
    source.write_text("old embed sentinel " * 80, encoding="utf-8")
    first = await ingest_path_async(str(source), collection_name=_COLLECTION)
    assert first["status"] == "ok"

    source.write_text("new embed sentinel " * 90, encoding="utf-8")

    def fail_embedding(nodes):
        raise RuntimeError("injected embedding failure")

    monkeypatch.setattr(replacement, "_embed_missing_nodes", fail_embedding)
    failed = await ingest_path_async(str(source), collection_name=_COLLECTION)

    assert failed["status"] == "error"
    assert failed["error_type"] == "embedding"
    texts = _source_texts(store, source)
    assert any("old embed sentinel" in text for text in texts)
    assert all("new embed sentinel" not in text for text in texts)


@pytest.mark.asyncio
async def test_partial_store_write_preserves_old_version_and_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An interrupted partial candidate coexists safely and a retry cleans it."""
    store = get_default_store()
    source = tmp_path / "partial-write.txt"
    source.write_text("old store sentinel " * 120, encoding="utf-8")
    first = await ingest_path_async(
        str(source),
        chunk_size=64,
        chunk_overlap=8,
        collection_name=_COLLECTION,
    )
    assert first["status"] == "ok"
    assert first["chunks_created"] > 1

    source.write_text("new store sentinel " * 150, encoding="utf-8")
    original_write = store.write_nodes

    def partial_then_fail(nodes, collection_name):
        original_write(nodes[:1], collection_name)
        raise RuntimeError("injected partial store write")

    monkeypatch.setattr(store, "write_nodes", partial_then_fail)
    failed = await ingest_path_async(
        str(source),
        chunk_size=64,
        chunk_overlap=8,
        collection_name=_COLLECTION,
    )

    assert failed["status"] == "error"
    texts_after_failure = _source_texts(store, source)
    assert any("old store sentinel" in text for text in texts_after_failure)

    monkeypatch.setattr(store, "write_nodes", original_write)
    recovered = await ingest_path_async(
        str(source),
        chunk_size=64,
        chunk_overlap=8,
        collection_name=_COLLECTION,
    )

    assert recovered["status"] == "ok"
    assert recovered["files_indexed"] == 1
    texts_after_recovery = _source_texts(store, source)
    assert texts_after_recovery
    assert all("old store sentinel" not in text for text in texts_after_recovery)
    assert any("new store sentinel" in text for text in texts_after_recovery)


@pytest.mark.asyncio
async def test_cleanup_failure_with_old_and_new_versions_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verified old+new coexistence is detected as incomplete and retried."""
    store = get_default_store()
    source = tmp_path / "cleanup-recovery.txt"
    source.write_text("old cleanup sentinel " * 100, encoding="utf-8")
    first = await ingest_path_async(str(source), collection_name=_COLLECTION)
    assert first["status"] == "ok"

    source.write_text("new cleanup sentinel " * 110, encoding="utf-8")
    original_delete = store.delete_ids

    def fail_stale_cleanup(collection_name, ids):
        raise RuntimeError("injected stale cleanup failure")

    monkeypatch.setattr(store, "delete_ids", fail_stale_cleanup)
    failed = await ingest_path_async(str(source), collection_name=_COLLECTION)

    assert failed["status"] == "error"
    mixed_texts = _source_texts(store, source)
    assert any("old cleanup sentinel" in text for text in mixed_texts)
    assert any("new cleanup sentinel" in text for text in mixed_texts)

    monkeypatch.setattr(store, "delete_ids", original_delete)
    recovered = await ingest_path_async(str(source), collection_name=_COLLECTION)

    assert recovered["status"] == "ok"
    assert recovered["files_indexed"] == 1
    final_texts = _source_texts(store, source)
    assert final_texts
    assert all("old cleanup sentinel" not in text for text in final_texts)
    assert any("new cleanup sentinel" in text for text in final_texts)


@pytest.mark.asyncio
@pytest.mark.parametrize("file_count", [5, 40])
async def test_generated_corpus_retains_only_one_source_node_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    file_count: int,
) -> None:
    """Peak live mock nodes is bounded by one file, not directory size."""
    from rag_mcp.core.codebase import codebase_map
    from rag_mcp.core.ingestion import pipeline

    for index in range(file_count):
        (tmp_path / f"doc-{index:03d}.txt").write_text(
            f"generated source {index}",
            encoding="utf-8",
        )

    class TrackedNode:
        pass

    node_count = 7
    alive = 0
    max_alive = 0

    def released() -> None:
        nonlocal alive
        alive -= 1

    async def fake_read(*args, **kwargs):
        nonlocal alive, max_alive
        gc.collect()
        nodes = []
        for _ in range(node_count):
            node = TrackedNode()
            alive += 1
            max_alive = max(max_alive, alive)
            weakref.finalize(node, released)
            nodes.append(node)
        return nodes

    class FakeTimings:
        def as_dict(self) -> dict[str, float]:
            return {
                "embedding_seconds": 0.0,
                "store_write_seconds": 0.0,
                "lock_wait_seconds": 0.0,
                "cleanup_seconds": 0.0,
            }

    async def fake_replace(nodes, **kwargs):
        await asyncio.sleep(0)
        return SimpleNamespace(
            chunks_written=len(nodes),
            chunks_removed=0,
            timings=FakeTimings(),
        )

    # The lineage compatibility guard probes collection existence before
    # any parse; an absent collection makes it a no-op for this fake store.
    fake_store = SimpleNamespace(collection_exists=lambda name: False)

    monkeypatch.setattr(
        codebase_map,
        "detect_file_types",
        lambda path: SimpleNamespace(entries=[]),
    )
    monkeypatch.setattr(pipeline, "get_default_store", lambda: fake_store)
    monkeypatch.setattr(
        pipeline,
        "is_complete_current_version",
        lambda *args, **kwargs: (False, 0),
    )
    monkeypatch.setattr(pipeline, "read_and_chunk_file_async", fake_read)
    monkeypatch.setattr(pipeline, "replace_source_nodes_async", fake_replace)

    result = await ingest_path_async(str(tmp_path), collection_name=_COLLECTION)
    gc.collect()

    assert result["status"] == "ok"
    assert result["files_indexed"] == file_count
    assert max_alive == node_count
    assert alive == 0


@pytest.mark.asyncio
async def test_ingestion_exposes_stage_timings_and_peak_rss(tmp_path: Path) -> None:
    """Successful bounded units expose attribution needed by Stage 3 experiments."""
    source = tmp_path / "timed.txt"
    source.write_text("timed source " * 100, encoding="utf-8")

    result = await ingest_path_async(str(source), collection_name=_COLLECTION)

    assert result["status"] == "ok"
    for key in (
        "change_detection_seconds",
        "parse_chunk_seconds",
        "embedding_seconds",
        "store_write_seconds",
        "lock_wait_seconds",
        "cleanup_seconds",
        "total_seconds",
    ):
        assert key in result["timings"]
        assert result["timings"][key] >= 0.0
    assert result["file_details"][0]["timings"]["total_seconds"] >= 0.0
    peak = result["peak_rss_bytes"]
    assert peak is None or peak > 0
    direct_peak = sample_peak_rss_bytes()
    assert direct_peak is None or direct_peak > 0
