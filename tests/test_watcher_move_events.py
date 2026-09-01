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
