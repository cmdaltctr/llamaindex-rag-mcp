"""Delete-then-ingest handling for file moves (design D5 of the
``fix-retrieval-freshness-and-context-assembly-2`` change).

Extracted from ``watcher.py`` so the handler stays under the 500-line
file ceiling. ``on_moved`` reuses the existing delete and ingest paths:
the old path is cleaned up first and the destination ingest is scheduled
only after that cleanup succeeds, so a source is never indexed under
two path identities at once.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# A failed old-path cleanup is retried this many times, spaced by the
# debounce window, before the watcher gives up and reports; the
# destination ingest stays deferred throughout (design D5).
MAX_MOVE_CLEANUP_RETRIES = 3


class MoveHandlingMixin:
    """Deletion and move coordination hosted by the ingest handler.

    The host supplies the debounce window, the shared timer registry,
    the hash cache, the state locks, and the ingest scheduler this
    mixin coordinates. Registering the retry timer in the host's
    ``_timers`` keeps ``stop()`` cancellation and the per-path debounce
    reset semantics in one place.
    """

    # Supplied by the concrete handler.
    debounce_seconds: float
    _collection_name: str
    _timers: dict[str, threading.Timer]
    _hash_cache: dict[str, str]
    _state_lock: threading.Lock
    _shutdown_requested: threading.Event

    _schedule_ingest: Callable[[str], None]

    # ── Move handler ────────────────────────────────────────────────────

    def on_moved(self, event) -> None:  # type: ignore[override]
        """Handle a rename or move as delete-then-ingest.

        The old path's chunks are removed first; the destination is
        ingested only once that cleanup succeeds. A destination
        resolving outside the watch root is rejected by the traversal
        guard inside the host's ``_do_ingest`` — the delete stays
        applied, which is the correct outcome for a move out of the
        tree.
        """
        if self._shutdown_requested.is_set():
            return
        self._handle_move(event.src_path, event.dest_path, attempt=1)

    def _handle_move(self, src_path: str, dest_path: str, attempt: int) -> None:
        """Run one move attempt: old-path cleanup, then destination ingest.

        A failed cleanup is never treated as success — the destination
        ingest is deferred and the cleanup retried (``_defer_move``).
        """
        if self._do_delete(src_path):
            logger.info(
                "Move handled: %s -> %s (destination ingest scheduled)",
                src_path,
                dest_path,
            )
            self._schedule_ingest(dest_path)
            return
        self._defer_move(src_path, dest_path, attempt)

    def _defer_move(self, src_path: str, dest_path: str, attempt: int) -> None:
        """Retry a failed move cleanup after the debounce window.

        The retry timer is keyed by the source path so a genuine
        re-creation at the old path supersedes it — the replacement path
        removes that source's stale rows itself — while ``stop()``
        cancels it with every other timer. After the final attempt the
        failure is reported and the move left pending; the destination
        is never ingested before the old path is confirmed clean.
        """
        if self._shutdown_requested.is_set():
            return
        if attempt >= MAX_MOVE_CLEANUP_RETRIES:
            logger.error(
                "Move %s -> %s: old-path cleanup failed after %d attempts; "
                "destination ingest left pending — chunks indexed under the "
                "old path remain until its next delete or ingest",
                src_path,
                dest_path,
                attempt,
            )
            return
        logger.warning(
            "Move %s -> %s: old-path cleanup failed (attempt %d/%d); "
            "destination ingest deferred until it succeeds",
            src_path,
            dest_path,
            attempt,
            MAX_MOVE_CLEANUP_RETRIES,
        )
        timer = threading.Timer(
            self.debounce_seconds,
            self._handle_move,
            args=[src_path, dest_path, attempt + 1],
        )
        timer.daemon = True
        with self._state_lock:
            self._timers[src_path] = timer
        timer.start()

    # ── Deletion handler ────────────────────────────────────────────────

    def _do_delete(self, file_path: str) -> bool:
        """Delete vectors for a file path and clean up pending state.

        Cancels any pending ingest timer for the path, clears its hash
        cache entry (so a later re-creation there is not skipped as
        unchanged), and removes the path's chunks from the store.
        Idempotent — safe to call even if the file was never ingested.

        Returns:
            True when cleanup succeeded. A zero-row removal and a removal
            against an absent collection both count as success — nothing
            was indexed under this path, so a move may proceed to ingest
            its destination. False when removal failed or shutdown was
            requested; callers must not treat the old path as cleaned.
        """
        if self._shutdown_requested.is_set():
            return False

        # Cancel any pending ingest timer for this file
        with self._state_lock:
            old_timer = self._timers.pop(file_path, None)
            if old_timer is not None:
                old_timer.cancel()
                logger.debug(
                    "Cancelled pending ingest timer for deleted file: %s",
                    file_path,
                )

        # Clear hash cache entry. ``_do_ingest`` keys the cache by the
        # RESOLVED path while event paths may carry symlinked components
        # (macOS ``/tmp`` → ``/private/tmp``), so both spellings are
        # popped — a surviving entry would skip a later re-creation at
        # this path as unchanged (task 6.3).
        cache_keys = {file_path, str(Path(file_path).resolve(strict=False))}
        with self._state_lock:
            for cache_key in cache_keys:
                if self._hash_cache.pop(cache_key, None) is not None:
                    logger.debug(
                        "Cleared hash cache for deleted file: %s",
                        cache_key,
                    )

        # Remove vectors from the store
        try:
            from ..core.ingestion import remove_document

            result = remove_document(file_path, collection_name=self._collection_name)
            if result.get("status") == "ok":
                removed = result.get("chunks_removed", 0)
                logger.info(
                    "Auto-removed %s — %d chunk(s) deleted",
                    Path(file_path).name,
                    removed,
                )
                return True
            # An error naming an absent collection means nothing was ever
            # indexed anywhere in it: removal is vacuously complete rather
            # than failed, so a move may still ingest its destination.
            # ``remove_document`` reports that case as an error for CLI
            # callers; the watcher only cares whether anything remains
            # indexed under the path.
            if not self._collection_present():
                logger.debug(
                    "Collection %r absent; nothing indexed to remove for %s",
                    self._collection_name,
                    file_path,
                )
                return True
            logger.warning(
                "Failed to remove deleted file %s: %s",
                file_path,
                result.get("message", "unknown error"),
            )
            return False
        except Exception as exc:
            logger.warning(
                "Failed to remove deleted file %s: %s",
                file_path,
                exc,
            )
            return False

    def _collection_present(self) -> bool:
        """Return whether the target collection exists in the default store.

        Advisory only: a probe failure reads as ``True`` so the caller
        keeps the conservative failure path rather than assuming a
        vacuous cleanup.
        """
        try:
            from ..core.vectordb import get_default_store

            return get_default_store().collection_exists(self._collection_name)
        except Exception as exc:  # noqa: BLE001 - probe is advisory
            logger.debug("Collection existence check failed: %s", exc)
            return True
