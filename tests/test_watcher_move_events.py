"""Red-first coverage for watcher handling of move events.

Stage 1 of the OpenSpec change
``fix-retrieval-freshness-and-context-assembly-2`` (task 1.3).

``DocumentIngestHandler`` implements ``on_created``, ``on_modified`` and
``on_deleted`` but not ``on_moved``: a rename inside the watch tree fires
neither a delete nor an ingest, so the old path's chunks stay indexed and
the new path is never indexed. This test pins the post-fix behaviour
(stage 6) against the real tmp-path Lance store and is EXPECTED TO FAIL
until ``on_moved`` lands.
"""

from __future__ import annotations

import logging
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileSystemMovedEvent

from rag_mcp.daemon.watcher import DocumentIngestHandler

# Content must contain a unique token so presence under the new path is
# distinguishable from any other row in the collection.
_DOC_CONTENT = (
    "Watcher move probe document. It carries the unique token "
    "watchmove-zebra-42 so its chunks are identifiable. "
    "Further sentences pad the document so the chunker produces "
    "several chunks with the default overlap. "
) * 3


class _FakeTimer:
    """A ``threading.Timer`` substitute fired manually by the test."""

    def __init__(self, interval, function, args=None, kwargs=None):
        self.interval = interval
        self.function = function
        self.args = args or []
        self.kwargs = kwargs or {}
        self._cancelled = False

    def start(self) -> None:
        pass

    def cancel(self) -> None:
        self._cancelled = True

    def fire(self) -> None:
        """Run the scheduled callback immediately unless cancelled."""
        if not self._cancelled:
            self.function(*self.args, **self.kwargs)


def _fire_all_timers(handler: DocumentIngestHandler) -> None:
    """Fire every pending debounce timer once, snapshotting the registry."""
    for _path, timer in list(handler._timers.items()):
        timer.fire()
    handler._timers.clear()


def _chunks_by_file_path(collection: str, file_path: str) -> list[tuple[str, dict]]:
    """Return ``(text, metadata)`` for stored chunks whose ``file_path`` matches."""
    from rag_mcp.core.vectordb import get_default_store

    return [
        (text, metadata)
        for _row_id, text, metadata in get_default_store().iter_documents(collection)
        if metadata.get("file_path") == file_path
    ]


def test_rename_inside_watch_tree_reindexes_under_new_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A move inside the tree must remove old-path chunks and index the new path.

    GIVEN a supported file ingested under ``old.txt`` inside the watch tree
    WHEN the file is renamed to ``new.txt`` inside the same tree
    THEN the old path's chunks are gone from the collection
    AND the new path's chunks are present.
    """
    monkeypatch.setattr(
        "rag_mcp.daemon.watcher.threading.Timer",
        _FakeTimer,
    )
    watch_root = tmp_path / "docs"
    watch_root.mkdir()
    source = watch_root / "old_name.txt"
    source.write_text(_DOC_CONTENT)

    handler = DocumentIngestHandler(
        debounce_seconds=0.01,
        watch_root=watch_root.resolve(),
        collection_name="documents",
        extensions={".txt"},
    )

    # Ingest the original path through the watcher's created path so the
    # collection holds chunks under the old path identity.
    handler.on_created(FileCreatedEvent(str(source)))
    _fire_all_timers(handler)

    old_chunks = _chunks_by_file_path("documents", str(source.resolve()))
    assert old_chunks, "precondition failed: the original path was never ingested"

    destination = watch_root / "new_name.txt"
    source.rename(destination)
    handler.on_moved(FileSystemMovedEvent(str(source), str(destination)))
    _fire_all_timers(handler)

    remaining_old = _chunks_by_file_path("documents", str(source.resolve()))
    new_chunks = _chunks_by_file_path("documents", str(destination.resolve()))

    assert not remaining_old, (
        f"{len(remaining_old)} chunk(s) remain indexed under the old path "
        f"{source}; a move must remove them."
    )
    assert new_chunks, (
        f"no chunks are indexed under the new path {destination}; a move must ingest it."
    )
    assert any("watchmove-zebra-42" in text for text, _meta in new_chunks), (
        "the new path's chunks must carry the moved document's content."
    )


def _make_handler(
    monkeypatch,
    watch_root: Path,
) -> DocumentIngestHandler:
    """Build a handler whose debounce and move-retry timers are fake."""
    # Both spellings are patched: debounce timers are created in
    # watcher.py, move-cleanup retries in move_handling.py.
    monkeypatch.setattr("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    monkeypatch.setattr("rag_mcp.daemon.move_handling.threading.Timer", _FakeTimer)
    return DocumentIngestHandler(
        debounce_seconds=0.01,
        watch_root=watch_root.resolve(),
        collection_name="documents",
        extensions={".txt"},
    )


def _fire_timer(handler: DocumentIngestHandler, path: str) -> None:
    """Fire and remove exactly one pending timer, unlike the fire-all helper."""
    timer = handler._timers.get(path)
    assert timer is not None, f"no pending timer for {path}: {list(handler._timers)}"
    del handler._timers[path]
    timer.fire()


def _ingest_via_watcher(handler: DocumentIngestHandler, path: Path, caplog) -> None:
    """Ingest a file through the created-event path and assert it landed."""
    with caplog.at_level(logging.INFO, logger="rag_mcp.daemon.watcher"):
        handler.on_created(FileCreatedEvent(str(path)))
        _fire_all_timers(handler)
    assert _chunks_by_file_path("documents", str(path.resolve())), (
        f"precondition failed: {path} was never ingested"
    )


def test_move_out_of_watch_tree_removes_chunks_and_rejects_destination(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    """Moving out of the tree removes the old path and never ingests the destination.

    GIVEN a supported file indexed at path A inside the watch tree
    WHEN it is moved to a destination outside the watch tree
    THEN the chunks for A are removed
    AND the traversal guard inside the ingest path rejects the destination.
    """
    watch_root = tmp_path / "docs"
    watch_root.mkdir()
    source = watch_root / "leaving.txt"
    source.write_text(_DOC_CONTENT)
    handler = _make_handler(monkeypatch, watch_root)
    _ingest_via_watcher(handler, source, caplog)

    outside = tmp_path / "elsewhere"
    outside.mkdir()
    destination = outside / "moved_out.txt"
    source.rename(destination)
    with caplog.at_level(logging.INFO, logger="rag_mcp.daemon.watcher"):
        handler.on_moved(FileSystemMovedEvent(str(source), str(destination)))
        _fire_all_timers(handler)

    assert not _chunks_by_file_path("documents", str(source.resolve())), (
        "a move out of the tree must still remove the old path's chunks."
    )
    assert not _chunks_by_file_path("documents", str(destination.resolve())), (
        "a destination outside the watch root must never be ingested."
    )
    assert any("Path traversal blocked" in record.message for record in caplog.records), (
        "the existing traversal guard is what rejected the destination."
    )


def test_move_into_watch_tree_ingests_destination(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    """Moving an outside file into the tree ingests it under the new path.

    GIVEN a supported file outside the watch tree, never indexed
    WHEN it is moved to a path inside the watch tree
    THEN it is ingested under its new path (an empty store is no obstacle:
    the removal step treats an absent collection as a zero-row no-op).
    """
    watch_root = tmp_path / "docs"
    watch_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    source = outside / "incoming.txt"
    source.write_text(_DOC_CONTENT)
    handler = _make_handler(monkeypatch, watch_root)

    destination = watch_root / "arrived.txt"
    source.rename(destination)
    with caplog.at_level(logging.INFO, logger="rag_mcp.daemon.watcher"):
        handler.on_moved(FileSystemMovedEvent(str(source), str(destination)))
        _fire_all_timers(handler)

    new_chunks = _chunks_by_file_path("documents", str(destination.resolve()))
    assert new_chunks, "a move into the tree must ingest the destination."
    assert any("watchmove-zebra-42" in text for text, _meta in new_chunks)


def test_move_of_unindexed_file_is_reported_noop(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    """Moving a never-ingested file reports zero chunks removed and does not raise.

    GIVEN a supported file inside the watch tree that was never ingested
    WHEN it is moved
    THEN the removal step reports zero chunks removed without raising
    AND the destination is still ingested.
    """
    watch_root = tmp_path / "docs"
    watch_root.mkdir()
    other = watch_root / "other.txt"  # makes the collection exist
    other.write_text(_DOC_CONTENT)
    unindexed = watch_root / "unindexed.txt"
    unindexed.write_text("Never ingested before its move. Uniquetoken noop-move-7.")
    handler = _make_handler(monkeypatch, watch_root)
    _ingest_via_watcher(handler, other, caplog)

    destination = watch_root / "now_indexed.txt"
    unindexed.rename(destination)
    with caplog.at_level(logging.INFO, logger="rag_mcp.daemon.move_handling"):
        handler.on_moved(FileSystemMovedEvent(str(unindexed), str(destination)))
        _fire_all_timers(handler)

    assert any("0 chunk(s) deleted" in record.message for record in caplog.records), (
        "the removal step must report zero chunks removed, not raise or fail."
    )
    assert _chunks_by_file_path("documents", str(destination.resolve())), (
        "the moved file itself must be ingested under its new path."
    )


def test_failed_cleanup_never_ingests_destination_and_is_retried(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    """A failed old-path cleanup defers the destination ingest and retries.

    GIVEN a watched file indexed at path A
    WHEN it is moved to path B and deletion of A fails once
    THEN B is not ingested as though the move completed
    AND the failure is observable and a retry is pending
    AND once the retry's cleanup succeeds, B is ingested.
    """
    from rag_mcp.core.ingestion import remove_document as real_remove_document

    watch_root = tmp_path / "docs"
    watch_root.mkdir()
    source = watch_root / "forked.txt"
    source.write_text(_DOC_CONTENT)
    handler = _make_handler(monkeypatch, watch_root)
    _ingest_via_watcher(handler, source, caplog)

    failures = {"remaining": 1}

    def _flaky_remove_document(file_path, collection_name="documents", store=None):
        if failures["remaining"] > 0:
            failures["remaining"] -= 1
            return {
                "status": "error",
                "message": "injected cleanup failure",
                "chunks_removed": 0,
                "collection": collection_name,
            }
        return real_remove_document(file_path, collection_name=collection_name, store=store)

    monkeypatch.setattr("rag_mcp.core.ingestion.remove_document", _flaky_remove_document)

    destination = watch_root / "destination.txt"
    source.rename(destination)
    with caplog.at_level(logging.INFO, logger="rag_mcp.daemon.move_handling"):
        handler.on_moved(FileSystemMovedEvent(str(source), str(destination)))

    # While cleanup failed: no destination ingest is scheduled or run…
    assert str(destination) not in handler._timers
    assert not _chunks_by_file_path("documents", str(destination.resolve())), (
        "the destination must not be ingested while old-path cleanup failed."
    )
    # …the failure is observable…
    assert any("destination ingest deferred" in record.message for record in caplog.records), (
        "the cleanup failure must be reported."
    )
    # …and a retry is pending for the old path.
    assert str(source) in handler._timers, "a cleanup retry must be scheduled."

    _fire_timer(handler, str(source))  # retry: cleanup now succeeds
    assert str(destination) in handler._timers, (
        "a successful cleanup must schedule the destination ingest."
    )
    _fire_timer(handler, str(destination))  # destination ingest runs

    assert not _chunks_by_file_path("documents", str(source.resolve()))
    assert _chunks_by_file_path("documents", str(destination.resolve())), (
        "the destination must be ingested once cleanup succeeded."
    )


def test_recreated_old_path_after_move_is_ingested_not_skipped(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    """A re-creation at the old path is not skipped as unchanged.

    GIVEN a file indexed at path A, then moved to B (hash cache cleared
    for A by the move's cleanup)
    WHEN a new file with identical content is created at A
    THEN it is ingested — the stale hash-cache entry for A must not
    suppress it as "unchanged".
    """
    watch_root = tmp_path / "docs"
    watch_root.mkdir()
    source = watch_root / "original.txt"
    source.write_text(_DOC_CONTENT)
    handler = _make_handler(monkeypatch, watch_root)
    _ingest_via_watcher(handler, source, caplog)
    assert handler._hash_cache, "precondition failed: hash cache is empty"

    destination = watch_root / "moved_on.txt"
    source.rename(destination)
    with caplog.at_level(logging.INFO, logger="rag_mcp.daemon.watcher"):
        handler.on_moved(FileSystemMovedEvent(str(source), str(destination)))
        _fire_all_timers(handler)

    # Re-create the old path with byte-identical content.
    source.write_text(_DOC_CONTENT)
    with caplog.at_level(logging.INFO, logger="rag_mcp.daemon.watcher"):
        handler.on_created(FileCreatedEvent(str(source)))
        _fire_all_timers(handler)

    assert _chunks_by_file_path("documents", str(source.resolve())), (
        "re-creation at the old path must be ingested, not skipped as "
        "unchanged by a stale hash-cache entry."
    )
    assert _chunks_by_file_path("documents", str(destination.resolve())), (
        "the moved destination must still be indexed."
    )


def test_persistent_cleanup_failure_exhausts_retries_and_leaves_move_pending(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    """A persistently failing cleanup exhausts its retries and reports.

    GIVEN a watched file indexed at path A
    WHEN it is moved to path B and deletion of A keeps failing
    THEN the retries are exhausted, the failure is escalated visibly,
    AND the move is left pending: B is never ingested while A's chunks
    remain — a reported fork risk, never a silent one.
    """
    watch_root = tmp_path / "docs"
    watch_root.mkdir()
    source = watch_root / "persistent.txt"
    source.write_text(_DOC_CONTENT)
    handler = _make_handler(monkeypatch, watch_root)
    _ingest_via_watcher(handler, source, caplog)

    monkeypatch.setattr(
        "rag_mcp.core.ingestion.remove_document",
        lambda file_path, collection_name="documents", store=None: {
            "status": "error",
            "message": "injected persistent cleanup failure",
            "chunks_removed": 0,
            "collection": collection_name,
        },
    )

    destination = watch_root / "never_ingested.txt"
    source.rename(destination)
    with caplog.at_level(logging.INFO, logger="rag_mcp.daemon.move_handling"):
        handler.on_moved(FileSystemMovedEvent(str(source), str(destination)))
        # Drive every scheduled retry to exhaustion.
        while handler._timers:
            _fire_timer(handler, next(iter(handler._timers)))

    assert any("failed after 3 attempts" in record.message for record in caplog.records), (
        "retry exhaustion must be reported at error level."
    )
    assert not handler._timers, "no further work may be scheduled after exhaustion."
    assert _chunks_by_file_path("documents", str(source.resolve())), (
        "the old path's chunks remain — the pending state the spec allows."
    )
    assert not _chunks_by_file_path("documents", str(destination.resolve())), (
        "the destination must never be ingested while cleanup keeps failing."
    )
