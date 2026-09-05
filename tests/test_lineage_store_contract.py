"""Red-first store-contract tests for stable source/chunk lineage.

Pins ``openspec/changes/add-stable-source-chunk-lineage`` tasks 1.5, 1.6, and
1.8 against the real store implementations (the chroma/lancedb parametrisation
from ``tests/test_ingestion_stage3.py``):

- replacement safety: identical forced re-ingestion keeps stable chunk IDs but
  rotates attempt-specific row IDs, preserves the durable attempt until
  verification, and stays failure-safe at every existing injection point;
- persistence: every production row carries the complete lineage metadata and
  one complete ordered chunk set; stale cleanup is scoped to one source_id;
- lifecycle: listing, preview, deletion, and metadata filters resolve through
  the derived source_id, including equal-content sources at two paths.

``replace_source_nodes_async`` is imported at module level (it exists today);
its new required ``source_id`` keyword is exercised at call time, so the red
run fails with ``TypeError`` per scenario until the implementation lands.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from llama_index.core import Settings
from llama_index.core.schema import TextNode

from omrg.core.ingestion import ingest_path_async, pipeline
from omrg.core.ingestion.loader import list_documents
from omrg.core.ingestion.replacement import IngestionStageError, replace_source_nodes_async
from omrg.core.ingestion.writer import preview_delete, remove_document
from omrg.core.vectordb import get_default_store, set_default_store
from omrg.core.vectordb.lancedb import LanceVectorStore

_COLLECTION = "lineage_store"


def _expected_source_id(canonical_file_path: str) -> str:
    """Return the spec-pinned source_id digest for one canonical path."""
    return "src_" + hashlib.sha256(("file\0" + canonical_file_path).encode("utf-8")).hexdigest()


@pytest.fixture(params=["chroma", "lancedb"])
def lineage_store(request: pytest.FixtureRequest, tmp_path: Path):
    """Install one real store implementation behind the process default."""
    if request.param == "chroma":
        return get_default_store()
    store = LanceVectorStore(uri=str(tmp_path / "lineage-lancedb"))
    set_default_store(store)
    return store


def _stored_rows(store, collection_name: str = _COLLECTION) -> list[tuple[str, str, dict]]:
    """Return every stored row as ``(row_id, text, metadata)``."""
    return list(store.iter_documents(collection_name))


def _make_nodes(texts: list[str], file_path: str) -> list[TextNode]:
    """Build fresh un-embedded nodes for one direct replacement attempt."""
    return [TextNode(text=text, metadata={"file_path": file_path}) for text in texts]


async def _replace(store, nodes: list[TextNode], *, file_path: str, source_id: str):
    """Run one direct replacement attempt with fixed version identities."""
    return await replace_source_nodes_async(
        nodes,
        file_path=file_path,
        source_id=source_id,
        content_hash="c" * 64,
        index_identity="i" * 64,
        source_version="v" * 64,
        collection_name=_COLLECTION,
        store=store,
    )


def _inject_failure(store, monkeypatch: pytest.MonkeyPatch, injection: str) -> None:
    """Break exactly one replacement stage for the next candidate attempt."""
    if injection == "embedding":

        def fail_embed(*args, **kwargs):
            raise RuntimeError("injected embedding failure")

        # MockEmbedding is a pydantic model, so the method is patched on the
        # class: instance-level attribute assignment is rejected by pydantic.
        monkeypatch.setattr(type(Settings.embed_model), "get_text_embedding_batch", fail_embed)
    elif injection == "store_write":

        def fail_write(nodes, collection_name):
            raise RuntimeError("injected store write failure")

        monkeypatch.setattr(store, "write_nodes", fail_write)
    elif injection == "store_verify":

        def fail_count(collection_name, where):
            raise RuntimeError("injected verification failure")

        monkeypatch.setattr(store, "count_where", fail_count)
    elif injection == "stale_cleanup":

        def fail_delete(collection_name, ids):
            raise RuntimeError("injected stale cleanup failure")

        monkeypatch.setattr(store, "delete_ids", fail_delete)


# ── Task 1.5: replacement regressions ────────────────────────────────────


class TestReplacementRegressions:
    """Stable chunk identity, rotated row identity, and failure safety."""

    _TEXTS = [f"replacement chunk {position} body" for position in range(3)]

    async def test_identical_reingest_keeps_chunk_ids_and_rotates_row_ids(
        self, tmp_path: Path, lineage_store
    ) -> None:
        """Spec: candidate chunk_ids repeat while row ids are attempt-specific."""
        file_path = str(tmp_path / "forced.txt")
        source_id = _expected_source_id(file_path)
        store = lineage_store

        first = await _replace(
            store, _make_nodes(self._TEXTS, file_path), file_path=file_path, source_id=source_id
        )
        rows_first = _stored_rows(store)
        first_row_ids = {row_id for row_id, _, _ in rows_first}

        second = await _replace(
            store, _make_nodes(self._TEXTS, file_path), file_path=file_path, source_id=source_id
        )
        rows_second = _stored_rows(store)

        assert first.chunks_written == 3
        assert second.chunks_written == 3
        assert second.source_attempt != first.source_attempt
        assert len(rows_second) == 3
        assert {row_id for row_id, _, _ in rows_second}.isdisjoint(first_row_ids)
        assert sorted(meta["chunk_id"] for _, _, meta in rows_second) == sorted(
            meta["chunk_id"] for _, _, meta in rows_first
        )
        assert all(meta["source_attempt"] == second.source_attempt for _, _, meta in rows_second)

    async def test_write_failure_preserves_durable_identical_version(
        self, tmp_path: Path, lineage_store, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spec: a failed candidate leaves the old attempt searchable and complete."""
        file_path = str(tmp_path / "write-safe.txt")
        source_id = _expected_source_id(file_path)
        store = lineage_store
        await _replace(
            store, _make_nodes(self._TEXTS, file_path), file_path=file_path, source_id=source_id
        )
        durable = _stored_rows(store)

        def fail_write(nodes, collection_name):
            raise RuntimeError("injected store write failure")

        monkeypatch.setattr(store, "write_nodes", fail_write)
        with pytest.raises(IngestionStageError) as excinfo:
            await _replace(
                store, _make_nodes(self._TEXTS, file_path), file_path=file_path, source_id=source_id
            )
        assert excinfo.value.stage == "store_write"

        surviving = _stored_rows(store)
        assert sorted(surviving) == sorted(durable)
        assert sorted(meta["source_chunk_index"] for _, _, meta in surviving) == [0, 1, 2]

    @pytest.mark.parametrize(
        ("injection", "expected_stage"),
        [
            ("embedding", "embedding"),
            ("store_write", "store_write"),
            ("store_verify", "store_verify"),
            ("stale_cleanup", "stale_cleanup"),
        ],
    )
    async def test_candidate_failure_preserves_last_durable_version(
        self,
        tmp_path: Path,
        lineage_store,
        monkeypatch: pytest.MonkeyPatch,
        injection: str,
        expected_stage: str,
    ) -> None:
        """Spec: every injected failure point keeps the durable attempt intact."""
        file_path = str(tmp_path / "safe.txt")
        source_id = _expected_source_id(file_path)
        store = lineage_store
        first = await _replace(
            store, _make_nodes(self._TEXTS, file_path), file_path=file_path, source_id=source_id
        )
        durable = _stored_rows(store)

        _inject_failure(store, monkeypatch, injection)
        with pytest.raises(IngestionStageError) as excinfo:
            await _replace(
                store, _make_nodes(self._TEXTS, file_path), file_path=file_path, source_id=source_id
            )
        assert excinfo.value.stage == expected_stage

        surviving = _stored_rows(store)
        if injection in ("store_verify", "stale_cleanup"):
            # The verified candidate coexists with the untouched durable rows.
            assert len(surviving) == 6
        else:
            assert sorted(surviving) == sorted(durable)
        durable_metas = [
            meta for _, _, meta in surviving if meta["source_attempt"] == first.source_attempt
        ]
        assert len(durable_metas) == 3
        assert sorted(meta["source_chunk_index"] for meta in durable_metas) == [0, 1, 2]
        assert len({meta["chunk_id"] for meta in durable_metas}) == 3

    async def test_parse_failure_preserves_lineage_of_last_durable_version(
        self, tmp_path: Path, lineage_store, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spec: a pipeline-level parse failure keeps prior lineage searchable."""
        source = tmp_path / "parse-safe.txt"
        source.write_text("durable lineage sentinel " * 80, encoding="utf-8")
        first = await ingest_path_async(str(source), collection_name=_COLLECTION)
        assert first["status"] == "ok"
        durable = _stored_rows(lineage_store)
        assert durable

        source.write_text("candidate lineage sentinel " * 90, encoding="utf-8")

        async def fail_parse(*args, **kwargs):
            raise ValueError("injected parse failure")

        monkeypatch.setattr(pipeline, "read_and_chunk_file_async", fail_parse)
        failed = await ingest_path_async(str(source), collection_name=_COLLECTION)

        assert failed["status"] == "error"
        assert sorted(_stored_rows(lineage_store)) == sorted(durable)


# ── Task 1.6: persistence and source-scoped cleanup ──────────────────────

_REQUIRED_ROW_KEYS = {
    "file_path",
    "source_id",
    "chunk_id",
    "source_content_hash",
    "source_index_identity",
    "source_version",
    "source_attempt",
    "source_chunk_count",
    "source_chunk_index",
}


class TestStorePersistence:
    """Lineage persists through the real stores; cleanup stays source-scoped."""

    async def test_ingested_rows_persist_complete_lineage_metadata(
        self, tmp_path: Path, lineage_store
    ) -> None:
        """Spec: one complete ordered chunk set with every lineage field."""
        source = tmp_path / "persist.txt"
        source.write_text("lineage persistence sentinel " * 100, encoding="utf-8")
        file_path = str(source)

        result = await ingest_path_async(str(source), collection_name=_COLLECTION)
        assert result["status"] == "ok"

        rows = _stored_rows(lineage_store)
        assert rows
        for _, _, meta in rows:
            assert _REQUIRED_ROW_KEYS <= set(meta)
            assert meta["file_path"] == file_path
            assert meta["source_id"] == _expected_source_id(file_path)
            # Spec: one content-hash name, no document_hash alias.
            assert "document_hash" not in meta

        indices = sorted(meta["source_chunk_index"] for _, _, meta in rows)
        assert indices == list(range(len(rows)))
        assert len({meta["chunk_id"] for _, _, meta in rows}) == len(rows)
        assert all(meta["source_chunk_count"] == len(rows) for _, _, meta in rows)

    async def test_completeness_check_is_keyed_by_source_id(
        self, tmp_path: Path, lineage_store
    ) -> None:
        """Spec: unchanged-version selection resolves rows through source_id."""
        from omrg.core.ingestion import source_state

        source = tmp_path / "complete.txt"
        source.write_text("completeness sentinel " * 100, encoding="utf-8")
        result = await ingest_path_async(str(source), collection_name=_COLLECTION)
        assert result["status"] == "ok"
        rows = _stored_rows(lineage_store)
        meta = rows[0][2]

        complete, total = source_state.is_complete_current_version(
            lineage_store,
            _COLLECTION,
            source_id=meta["source_id"],
            content_hash=meta["source_content_hash"],
            index_identity=meta["source_index_identity"],
            source_version=meta["source_version"],
        )
        assert complete is True
        assert total == len(rows)

        other_complete, other_total = source_state.is_complete_current_version(
            lineage_store,
            _COLLECTION,
            source_id="src_" + "e" * 64,
            content_hash=meta["source_content_hash"],
            index_identity=meta["source_index_identity"],
            source_version=meta["source_version"],
        )
        assert other_complete is False
        assert other_total == 0

    async def test_version_change_cleanup_is_source_scoped(
        self, tmp_path: Path, lineage_store
    ) -> None:
        """Spec: replacing one source never touches an equal-bytes neighbour."""
        payload = "scoped cleanup sentinel paragraph " * 120
        first_file = tmp_path / "first-scoped.txt"
        second_file = tmp_path / "second-scoped.txt"
        first_file.write_text(payload, encoding="utf-8")
        second_file.write_text(payload, encoding="utf-8")

        await ingest_path_async(
            str(first_file), chunk_size=256, chunk_overlap=32, collection_name=_COLLECTION
        )
        await ingest_path_async(
            str(second_file), chunk_size=256, chunk_overlap=32, collection_name=_COLLECTION
        )

        sid_first = _expected_source_id(str(first_file))
        sid_second = _expected_source_id(str(second_file))
        rows = _stored_rows(lineage_store)
        rows_first_before = [row for row in rows if row[2]["source_id"] == sid_first]
        rows_second_before = [row for row in rows if row[2]["source_id"] == sid_second]
        assert rows_first_before and rows_second_before

        replaced = await ingest_path_async(
            str(first_file), chunk_size=96, chunk_overlap=12, collection_name=_COLLECTION
        )
        assert replaced["status"] == "ok"
        assert replaced["chunks_removed"] == len(rows_first_before)

        rows_after = _stored_rows(lineage_store)
        rows_second_after = [row for row in rows_after if row[2]["source_id"] == sid_second]
        rows_first_after = [row for row in rows_after if row[2]["source_id"] == sid_first]

        assert sorted(rows_second_after) == sorted(rows_second_before)
        assert rows_first_after
        assert all(meta["source_id"] == sid_first for _, _, meta in rows_first_after)
        assert all(
            meta["source_attempt"] != rows_first_before[0][2]["source_attempt"]
            for _, _, meta in rows_first_after
        )


# ── Task 1.8: listing, preview, deletion, and filters by source_id ───────


class TestLifecycle:
    """Listing, preview, deletion, and metadata filters use stable identity."""

    async def test_list_documents_groups_by_source_id_with_human_path(
        self, tmp_path: Path, lineage_store
    ) -> None:
        """Spec: one source_id lists once with its chunk count and human path."""
        source = tmp_path / "listed.txt"
        source.write_text("listing sentinel paragraph " * 240, encoding="utf-8")
        await ingest_path_async(str(source), collection_name=_COLLECTION)

        rows = list_documents(_COLLECTION, store=lineage_store)
        assert len(rows) == 1
        row = rows[0]
        assert set(row) == {"source", "source_id", "chunks", "orphaned"}
        assert row["orphaned"] is False
        assert row["source"] == str(source)
        assert row["source_id"] == _expected_source_id(str(source))
        assert row["chunks"] >= 2
        assert row["chunks"] == lineage_store.count_where(
            _COLLECTION, {"source_id": row["source_id"]}
        )

    async def test_equal_content_sources_list_separately(
        self, tmp_path: Path, lineage_store
    ) -> None:
        """Spec: equal bytes at two paths stay two listed sources."""
        payload = "equal bytes at two logical sources " * 100
        first = tmp_path / "equal-a.txt"
        second = tmp_path / "equal-b.txt"
        first.write_text(payload, encoding="utf-8")
        second.write_text(payload, encoding="utf-8")
        await ingest_path_async(str(first), collection_name=_COLLECTION)
        await ingest_path_async(str(second), collection_name=_COLLECTION)

        rows = list_documents(_COLLECTION, store=lineage_store)
        assert [row["source"] for row in rows] == sorted([str(first), str(second)])
        assert {row["source_id"] for row in rows} == {
            _expected_source_id(str(first)),
            _expected_source_id(str(second)),
        }

    async def test_preview_delete_canonicalises_the_requested_path(
        self, tmp_path: Path, lineage_store
    ) -> None:
        """Spec: deletion preview resolves the same derived source_id."""
        source = tmp_path / "previewed.txt"
        source.write_text("preview deletion sentinel " * 100, encoding="utf-8")
        await ingest_path_async(str(source), collection_name=_COLLECTION)
        chunk_count = lineage_store.count_where(
            _COLLECTION, {"source_id": _expected_source_id(str(source))}
        )

        # A redundant ``..`` spelling resolves to the same canonical path
        # (``"./" + absolute`` would be relative to the process CWD, which
        # is a different file and therefore a different source_id).
        redundant = str(tmp_path / ".." / tmp_path.name / "previewed.txt")
        for requested in (str(source), redundant):
            preview = preview_delete(
                path=requested, collection_name=_COLLECTION, store=lineage_store
            )
            assert preview["status"] == "ok"
            assert preview["mode"] == "path"
            assert preview["would_delete"] == chunk_count

    async def test_remove_document_deletes_derived_source_and_is_idempotent(
        self, tmp_path: Path, lineage_store
    ) -> None:
        """Spec: path deletion removes exactly the derived source's chunks."""
        first = tmp_path / "removed.txt"
        second = tmp_path / "kept.txt"
        payload = "path deletion sentinel paragraph " * 100
        first.write_text(payload, encoding="utf-8")
        second.write_text(payload, encoding="utf-8")
        await ingest_path_async(str(first), collection_name=_COLLECTION)
        await ingest_path_async(str(second), collection_name=_COLLECTION)

        sid_first = _expected_source_id(str(first))
        sid_second = _expected_source_id(str(second))
        chunks_first = lineage_store.count_where(_COLLECTION, {"source_id": sid_first})
        chunks_second = lineage_store.count_where(_COLLECTION, {"source_id": sid_second})

        removed = remove_document(str(first), _COLLECTION, store=lineage_store)
        assert removed["status"] == "ok"
        assert removed["chunks_removed"] == chunks_first
        assert removed["collection"] == _COLLECTION
        assert lineage_store.count_where(_COLLECTION, {"source_id": sid_first}) == 0
        assert lineage_store.count_where(_COLLECTION, {"source_id": sid_second}) == chunks_second

        again = remove_document(str(first), _COLLECTION, store=lineage_store)
        assert again["status"] == "ok"
        assert again["chunks_removed"] == 0

    async def test_remove_document_reports_missing_collection(
        self, tmp_path: Path, lineage_store
    ) -> None:
        """Spec: deleting from an absent collection is a descriptive error."""
        source = tmp_path / "absent-collection.txt"
        source.write_text("unused content", encoding="utf-8")
        result = remove_document(str(source), "lineage_absent", store=lineage_store)
        assert result["status"] == "error"
        assert result["message"]

    def test_invalid_path_returns_error_shapes_without_raising(self, lineage_store) -> None:
        """Invalid paths use the error-result contract; nothing is deleted.

        A path containing a NUL byte makes ``canonical_source_path`` raise
        ``ValueError``. Both deletion entry points must map that to their
        documented error dicts — the preview keeps ``dry_run: True`` and the
        deletion keeps ``chunks_removed: 0`` — instead of letting the
        exception escape the core layer.
        """
        lineage_store.create_collection(_COLLECTION)
        bad_path = "bad\0path.txt"

        preview = preview_delete(path=bad_path, collection_name=_COLLECTION, store=lineage_store)
        assert preview["status"] == "error"
        assert preview["dry_run"] is True
        assert preview["mode"] == "path"
        assert preview["would_delete"] == 0
        assert preview["message"]

        removal = remove_document(bad_path, _COLLECTION, store=lineage_store)
        assert removal["status"] == "error"
        assert removal["chunks_removed"] == 0
        assert removal["message"]

        assert lineage_store.count(_COLLECTION) == 0

    async def test_metadata_filters_select_lineage_fields(
        self, tmp_path: Path, lineage_store
    ) -> None:
        """Spec: existing metadata filters select source_id and chunk_id rows."""
        source = tmp_path / "filtered.txt"
        source.write_text("metadata filter sentinel paragraph " * 100, encoding="utf-8")
        await ingest_path_async(str(source), collection_name=_COLLECTION)

        sid = _expected_source_id(str(source))
        total = lineage_store.count(_COLLECTION)
        assert lineage_store.count_where(_COLLECTION, {"source_id": sid}) == total
        assert (
            lineage_store.count_where(
                _COLLECTION, {"source_version": _stored_rows(lineage_store)[0][2]["source_version"]}
            )
            == total
        )
        one_chunk_id = _stored_rows(lineage_store)[0][2]["chunk_id"]
        assert lineage_store.count_where(_COLLECTION, {"chunk_id": one_chunk_id}) == 1
