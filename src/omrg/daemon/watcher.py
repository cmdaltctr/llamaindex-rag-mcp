"""File system watcher for automatic document ingestion.

Monitors a directory tree for created, modified, deleted and moved
documents and auto-ingests them into the vector store using
``ingest_path_async()`` via ``asyncio.run()``.  Includes SHA-256
content-hash deduplication, per-file debouncing, ingestion throttling,
consecutive-error detection, and graceful shutdown on SIGINT.
Move (rename) events are handled as delete-then-ingest by
:class:`MoveHandlingMixin <omrg.daemon.move_handling.MoveHandlingMixin>`.

The watcher runs as a standalone CLI process (``rag-mcp watch``), not
inside the MCP server loop.  All ingestion is dispatched through
``asyncio.run(ingest_path_async(...))`` from the watcher thread.

Usage::

    rag-mcp watch /path/to/docs
    rag-mcp watch /path/to/docs --debounce 5
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Iterable
from pathlib import Path

from watchdog.events import PatternMatchingEventHandler

from ..core.ingestion.loader import SUPPORTED_EXTENSIONS
from ._shared import _sha256_file
from .move_handling import MoveHandlingMixin

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
DEFAULT_DEBOUNCE_SECONDS = 2.0
MIN_DEBOUNCE_SECONDS = 0.5
MAX_CONCURRENT_INGESTS = 2
CONSECUTIVE_ERROR_THRESHOLD = 5
MAX_SHUTDOWN_SECONDS = 30
MAX_HASH_CACHE_ENTRIES = 50_000


def resolve_watch_extensions(collection_name: str = "documents") -> set[str]:
    """Resolve the watch pattern set from the collection's profile.

    Watch and manual ingest MUST NOT diverge (design D4): both read the
    same profile-scoped ``ingestion.ingest_extensions`` set. A failing
    profile resolution (bad tag, unreadable bundle) falls back to the
    module constant default with a warning rather than refusing to
    watch — the ingest dispatch itself still resolves per call.

    Args:
        collection_name: The collection auto-ingested files route into.

    Returns:
        The resolved extension set to build watchdog patterns from.
    """
    try:
        from .. import compose

        effective = compose.build_profile_resolver().resolve(collection_name)
        return set(effective.ingestion.ingest_extensions)
    except Exception as exc:  # noqa: BLE001 - any resolution failure degrades
        logger.warning(
            "Could not resolve the extension set for collection %r (%s); "
            "watching the default set %s",
            collection_name,
            exc,
            sorted(SUPPORTED_EXTENSIONS),
        )
        return set(SUPPORTED_EXTENSIONS)


class DocumentIngestHandler(MoveHandlingMixin, PatternMatchingEventHandler):
    """Watchdog event handler that auto-ingests documents on change.

    Attributes:
        debounce_seconds: Quiet period before triggering ingestion.
        _collection_name: Vector-store collection to route into (default "documents").
        _timers: Per-file debounce timers.
        _hash_cache: Per-file SHA-256 content hashes.
        _ingest_semaphore: Limits concurrent ingest_path() calls.
        _consecutive_errors: Counter for consecutive ConnectionError failures.
    """

    def __init__(
        self,
        debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
        max_concurrent: int = MAX_CONCURRENT_INGESTS,
        watch_root: Path | None = None,
        collection_name: str = "documents",
        extensions: Iterable[str] | None = None,
    ) -> None:
        # Build patterns from the RESOLVED extension set (design D4) so
        # watch and manual ingest cannot diverge: callers pass the
        # collection profile's set (see resolve_watch_extensions); the
        # module constant is only the fallback for callers without one.
        resolved_extensions = (
            set(extensions) if extensions is not None else set(SUPPORTED_EXTENSIONS)
        )
        patterns = [f"*{ext}" for ext in sorted(resolved_extensions)]

        # Ignore hidden files, temp files, and .git directories
        ignore_patterns = [
            ".*",  # hidden files (.DS_Store, .gitkeep, etc.)
            "~$*",  # Office temporary files
            "*.tmp",  # generic temp files
            "*.part",  # incomplete downloads
        ]

        super().__init__(
            patterns=patterns,
            ignore_patterns=ignore_patterns,
            ignore_directories=True,
        )

        self.debounce_seconds = debounce_seconds
        self._watch_root = watch_root  # caller already resolves
        self._collection_name = collection_name
        self._timers: dict[str, threading.Timer] = {}
        # NOTE: Hash-cache race condition (acceptable for v1) — with
        # BoundedSemaphore(2), two threads can concurrently compute the
        # hash for the same file, both see it as changed, and both call
        # ingest_path() before either updates the cache.  This results in
        # at most one wasted embedding call.  ChromaDB upsert is
        # idempotent, so no data corruption occurs.  A threading.Lock
        # around the cache read/update would close the window but adds
        # complexity that is not justified for the expected workload.
        self._hash_cache: dict[str, str] = {}
        self._ingest_semaphore = threading.BoundedSemaphore(max_concurrent)
        self._consecutive_errors: int = 0
        self._in_flight_count: int = 0
        self._in_flight_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._error_counter_lock = threading.Lock()
        self._shutdown_requested = threading.Event()

    # ── Event handlers ───────────────────────────────────────────────────

    def on_created(self, event) -> None:  # type: ignore[override]
        """Route file creation events to debounced ingest."""
        self._schedule_ingest(event.src_path)

    def on_modified(self, event) -> None:  # type: ignore[override]
        """Route file modification events to debounced ingest."""
        self._schedule_ingest(event.src_path)

    def on_deleted(self, event) -> None:  # type: ignore[override]
        """Remove vectors when a supported file is deleted.

        Delegates to ``_do_delete`` (provided by
        :class:`MoveHandlingMixin`), which cancels any pending ingest
        timer for the deleted file, clears the hash cache entry, and
        removes the file's chunks from the store.  Deletion is immediate
        (no debouncing) — the ``on_deleted`` event fires only once per
        file deletion.
        """
        # The explicit result is intentionally unused here: a standalone
        # delete has no follow-up step to gate on it (unlike on_moved).
        self._do_delete(event.src_path)

    # ── Debounce scheduling ──────────────────────────────────────────────

    def _schedule_ingest(self, file_path: str) -> None:
        """Schedule debounced ingestion for *file_path*.

        Each new event for the same file resets the debounce timer.
        Ingestion fires only after the quiet period elapses.
        """
        if self._shutdown_requested.is_set():
            return

        with self._state_lock:
            # Cancel any existing timer for this file
            old_timer = self._timers.pop(file_path, None)
            if old_timer is not None:
                old_timer.cancel()
                logger.debug("Debounce timer reset for %s", file_path)

            timer = threading.Timer(
                self.debounce_seconds,
                self._do_ingest,
                args=[file_path],
            )
            timer.daemon = True
            self._timers[file_path] = timer
            timer.start()

    def _do_ingest(self, file_path: str) -> None:
        """Perform the actual ingestion after debounce completes.

        Checks content hash for deduplication, acquires the
        semaphore for throttling, and dispatches ``ingest_path_async()``
        via ``run_coroutine_threadsafe`` if a loop is available,
        otherwise falls back to sync ``ingest_path()``.
        """
        if self._shutdown_requested.is_set():
            return

        path = Path(file_path)

        # ── Symlink traversal protection ──────────────────────────────────
        if self._watch_root is not None:
            resolved = None  # always bound for except blocks
            try:
                resolved = path.resolve(strict=False)
                _ = resolved.relative_to(self._watch_root)
                # Reuse the resolved path for subsequent operations to
                # prevent TOCTOU races (symlink swap between check and use).
                path = resolved
                file_path = str(resolved)
            except ValueError:
                logger.warning(
                    "Path traversal blocked: %s resolves to %s outside watch root %s",
                    file_path,
                    resolved,
                    self._watch_root,
                )
                with self._state_lock:
                    self._timers.pop(file_path, None)
                    self._hash_cache.pop(file_path, None)
                return
            except OSError as exc:
                logger.warning(
                    "Cannot resolve path for traversal check: %s — %s",
                    file_path,
                    exc,
                )
                with self._state_lock:
                    self._timers.pop(file_path, None)
                return

        # ── Content-hash deduplication ───────────────────────────────────
        try:
            current_hash = _sha256_file(path)
        except FileNotFoundError:
            logger.debug("File vanished before debounce completed: %s", file_path)
            with self._state_lock:
                self._timers.pop(file_path, None)
                self._hash_cache.pop(file_path, None)
            return
        except OSError as exc:
            logger.warning("Cannot read file for hashing: %s — %s", file_path, exc)
            with self._state_lock:
                self._timers.pop(file_path, None)
            return

        cached_hash = self._hash_cache.get(file_path)
        if cached_hash == current_hash:
            logger.debug("Skipping unchanged file: %s", file_path)
            with self._state_lock:
                self._timers.pop(file_path, None)
            return

        # ── Throttled ingestion ──────────────────────────────────────────
        with self._ingest_semaphore:
            if self._shutdown_requested.is_set():
                return

            with self._in_flight_lock:
                self._in_flight_count += 1

            try:
                logger.info("Auto-ingesting %s…", file_path)

                self._dispatch_ingest(file_path, current_hash)

            finally:
                with self._in_flight_lock:
                    self._in_flight_count -= 1

        # Clean up timer entry
        with self._state_lock:
            self._timers.pop(file_path, None)

    def _dispatch_ingest(self, file_path: str, current_hash: str) -> None:
        """Run ingestion via asyncio.run from the watcher thread."""
        from .. import compose
        from ..core.ingestion import ingest_path_async

        # Phase 4: resolve the collection's profile for per-operation levers.
        try:
            effective = compose.build_profile_resolver().resolve(self._collection_name)
        except ValueError:
            effective = None

        try:
            result = asyncio.run(
                ingest_path_async(
                    file_path,
                    collection_name=self._collection_name,
                    effective_settings=effective,
                )
            )

            if result.get("status") == "error":
                error_msg = result.get("message", "unknown error")
                if result.get("error_type") == "connection":
                    raise ConnectionError(error_msg)
                raise RuntimeError(error_msg)

            chunks = result.get("chunks_created", 0)
            logger.info("Auto-ingested %s — %d chunk(s)", file_path, chunks)
            self._update_hash_cache(file_path, current_hash)
            with self._error_counter_lock:
                self._consecutive_errors = 0

        except ConnectionError as exc:
            self._handle_connection_error(file_path, exc)
        except RuntimeError as exc:
            self._handle_runtime_error(file_path, exc)
        except FileNotFoundError:
            logger.debug("File not found during ingestion (deleted): %s", file_path)
            with self._state_lock:
                self._hash_cache.pop(file_path, None)
                self._timers.pop(file_path, None)
        except Exception as exc:
            logger.warning("Ingestion failed for %s: %s", file_path, exc)

    def _update_hash_cache(self, file_path: str, current_hash: str) -> None:
        """Update hash cache with eviction if at capacity."""
        if file_path not in self._hash_cache and len(self._hash_cache) >= MAX_HASH_CACHE_ENTRIES:
            oldest = next(iter(self._hash_cache))
            del self._hash_cache[oldest]
        self._hash_cache[file_path] = current_hash

    def _handle_connection_error(self, file_path: str, exc: Exception) -> None:
        """Handle ConnectionError with consecutive-error tracking."""
        with self._error_counter_lock:
            self._consecutive_errors += 1
            current_errors = self._consecutive_errors
        logger.warning(
            "Ingestion failed (ConnectionError) for %s: %s [%d consecutive]",
            file_path,
            exc,
            current_errors,
        )
        if current_errors >= CONSECUTIVE_ERROR_THRESHOLD:
            logger.critical(
                "%d consecutive ConnectionError failures — "
                "Ollama may be unreachable. Check that Ollama "
                "is running and restart the watcher.",
                current_errors,
            )

    def _handle_runtime_error(self, file_path: str, exc: Exception) -> None:
        """Handle RuntimeError (non-connection failures)."""
        with self._error_counter_lock:
            self._consecutive_errors = 0
        logger.warning("Ingestion failed for %s: %s", file_path, exc)

    def stop(self) -> None:
        """Cancel all pending timers, wait for in-flight, then signal done.

        Shutdown sequence (as designed in the spec):
          1. Cancel all pending threading.Timer callbacks
          2. Wait for in-flight ingest_path() calls to complete,
             with a maximum wait of ``MAX_SHUTDOWN_SECONDS``
          3. Set _shutdown_requested as belt-and-suspenders
          4. (Observer stop is done by the caller)
        """
        # Step 1: Cancel all pending timers
        with self._state_lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()

        # Step 2: Wait for in-flight ingestion to complete (with deadline)
        deadline = time.monotonic() + MAX_SHUTDOWN_SECONDS
        while True:
            with self._in_flight_lock:
                if self._in_flight_count == 0:
                    break
            if time.monotonic() >= deadline:
                logger.warning(
                    "Shutdown timeout after %ds — abandoning %d in-flight ingestion(s)",
                    MAX_SHUTDOWN_SECONDS,
                    self._in_flight_count,
                )
                break
            time.sleep(0.1)

        # Step 3: Set shutdown flag as belt-and-suspenders
        self._shutdown_requested.set()

        logger.info("Watcher stopped — all pending work completed.")

    @property
    def in_flight_count(self) -> int:
        """Return the number of currently in-flight ingestions."""
        with self._in_flight_lock:
            return self._in_flight_count
