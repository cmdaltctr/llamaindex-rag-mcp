# Specification: watch-command

## Purpose

Define the `rag-mcp watch` command and file-system watcher behaviour for automatically ingesting, updating, and removing indexed document chunks as files change.
## Requirements
### Requirement: CLI subcommand `rag-mcp watch`

The system SHALL provide a `rag-mcp watch <path>` CLI subcommand that monitors a directory tree for supported document files and auto-ingests them into the vector-store index using the existing `ingest_path_async()` pipeline.

#### Scenario: Basic watch starts and waits
- **WHEN** the user runs `rag-mcp watch /path/to/docs`
- **THEN** the process SHALL block and monitor `/path/to/docs` for file system events
- **THEN** the process SHALL output a message like `Watching /path/to/docs for document changes…` to stderr

#### Scenario: Watch rejects non-existent path
- **WHEN** the user runs `rag-mcp watch /nonexistent/path`
- **THEN** the process SHALL print an error message to stderr and exit with a non-zero status code

### Requirement: File event filtering

The watcher SHALL respond to `on_created`, `on_modified`, `on_deleted`, AND `on_moved` file system events for files with supported extensions (as defined by the resolved ingestible extension set). The watcher SHALL ignore hidden files (names starting with `.`), temporary files (`~$*`, `*.tmp`, `*.part`), and `.git` directories.

`on_moved` was previously unhandled, so a rename inside the watch tree fired
neither a delete nor an ingest, leaving the old path indexed and the new path
absent.

#### Scenario: Ignores unsupported file types
- **WHEN** an unsupported file (e.g. `.png`, `.mp4`, `.DS_Store`) is created in the watched directory
- **THEN** the watcher SHALL NOT attempt to ingest it

#### Scenario: Ignores hidden and temp files
- **WHEN** a hidden file (e.g. `.gitkeep`) or a temporary file (e.g. `~$doc.docx`) is created or modified
- **THEN** the watcher SHALL NOT attempt to ingest it

#### Scenario: Move events are handled
- **WHEN** a supported file is renamed or moved within the watched tree
- **THEN** the watcher SHALL remove the chunks indexed under its previous path
- **AND** SHALL ingest it under its new path

### Requirement: Recursive directory watching

The watcher SHALL watch the given path recursively, monitoring all subdirectories by default.

#### Scenario: Detects files in subdirectories
- **WHEN** a supported file is created in a subdirectory of the watched path
- **THEN** the watcher SHALL detect the event and trigger ingestion

#### Scenario: Zotero storage structure
- **WHEN** Zotero creates a new paper in `storage/<hash>/<filename>.pdf`
- **THEN** the watcher SHALL detect the new PDF and trigger ingestion

### Requirement: Auto-removal of vectors on file deletion

The watcher SHALL handle `on_deleted` events from the watchdog library. When a supported file is deleted from the watched directory tree, the watcher SHALL automatically remove all its chunks from the vector store by calling `remove_document()` on the event's `src_path`. The handler SHALL also cancel any pending ingest timer for the same file path and clear its hash cache entry. Deletion SHALL NOT be debounced — it SHALL fire immediately on the `on_deleted` event.

#### Scenario: File deletion removes vectors
- **WHEN** a supported file (e.g. `paper.pdf`) is deleted from a watched directory
- **THEN** the watcher SHALL detect the deletion via `on_deleted`
- **THEN** the watcher SHALL cancel any pending ingest timer for that file path
- **THEN** the watcher SHALL clear the file's hash cache entry
- **THEN** the watcher SHALL call `remove_document()` to delete all chunks for that file from the vector store
- **THEN** the watcher SHALL log the deletion outcome at INFO level

#### Scenario: File deletion with no indexed chunks
- **WHEN** a supported file is deleted from a watched directory, but it was never successfully ingested (no chunks in the vector store)
- **THEN** the watcher SHALL still cancel pending timers and clear hash cache
- **THEN** `remove_document()` SHALL return `chunks_removed: 0`
- **THEN** the watcher SHALL NOT log an error — this is a normal state

#### Scenario: File deletion uses the handler's configured collection
- **WHEN** the watcher was started with `--collection research` and a file is deleted
- **THEN** chunks SHALL be removed from the `"research"` collection, not the default `"documents"` collection

#### Scenario: Unsupported file deletion is ignored
- **WHEN** an unsupported file (e.g. `.DS_Store`, `image.png`) is deleted from the watched directory
- **THEN** the watcher SHALL NOT call `remove_document()` (the event is filtered by `PatternMatchingEventHandler`)

#### Scenario: File deleted during debounce window
- **WHEN** a file is modified (triggering a debounce timer), then deleted before the timer fires
- **THEN** the `on_deleted` handler SHALL cancel the pending ingest timer
- **THEN** the `on_deleted` handler SHALL clear the hash cache entry
- **THEN** the `on_deleted` handler SHALL call `remove_document()` to clean up any previously-ingested chunks
- **THEN** the watcher SHALL NOT call `ingest_path_async()` for the deleted file (timer was cancelled)

### Requirement: Event debouncing

The watcher SHALL debounce file system events to avoid triggering ingestion during active writes (e.g. streaming writes, fragmented downloads). For each file path, a timer SHALL be reset on each new event and the ingestion SHALL only fire after a quiet period with no further events for that file. The default debounce interval SHALL be 2 seconds. The user SHALL be able to override this with a `--debounce <seconds>` flag.

#### Scenario: Debounces rapid successive events
- **WHEN** a file receives multiple `modified` events within the debounce window (e.g. during a streaming write)
- **THEN** the watcher SHALL wait until no new events arrive for the debounce interval before triggering ingestion
- **THEN** the watcher SHALL trigger ingestion exactly once

#### Scenario: Custom debounce interval
- **WHEN** the user runs `rag-mcp watch /path --debounce 5`
- **THEN** the watcher SHALL use a 5-second debounce interval

### Requirement: File size limit

The watcher SHALL reject files larger than a configurable maximum size (default 500 MB) before hashing. If a file exceeds the limit, the watcher SHALL log a WARNING-level message and skip ingestion. This prevents resource exhaustion (CPU, memory) from attempting to hash and embed multi-gigabyte files in the watched directory.

#### Scenario: Large file rejected before hashing
- **WHEN** a `modified` event fires for a supported file larger than 500 MB
- **THEN** the watcher SHALL NOT compute its SHA-256 hash
- **THEN** the watcher SHALL log a WARNING-level message indicating the file exceeds the maximum size
- **THEN** the watcher SHALL NOT call `ingest_path_async()` for that file

#### Scenario: Normal-sized file proceeds
- **WHEN** a `modified` event fires for a supported file under the size limit
- **THEN** the watcher SHALL proceed with hashing and ingestion as normal

### Requirement: Content-hash deduplication

The watcher SHALL compute a SHA-256 hash of each file before ingesting and store it in an in-memory cache. If a file event fires for a file whose content hash matches the cached hash, the watcher SHALL skip ingestion. The cache SHALL be ephemeral (lost on watcher restart — no persistent storage). On ingestion failure, the hash SHALL NOT be updated in the cache, so the next `modified` event for that file triggers a fresh attempt.

When file hashing fails with an `OSError` (e.g., permission denied), the watcher SHALL log a WARNING and SHALL clean up the stale timer entry for that file path. The hash cache SHALL be bounded — when it exceeds a configurable maximum number of entries (default 50 000), the least-recently-inserted entry SHALL be evicted.

#### Scenario: Skips unchanged content
- **WHEN** a `modified` event fires for a file whose content has not actually changed
- **THEN** the watcher SHALL skip ingestion and log a debug message

#### Scenario: Ingests genuinely changed content
- **WHEN** a `modified` event fires for a file whose content has genuinely changed (different hash)
- **THEN** the watcher SHALL proceed with ingestion and update the cached hash

#### Scenario: OSError during hashing cleans up timer
- **WHEN** file hashing raises `OSError` (e.g., permission denied)
- **THEN** the watcher SHALL log a WARNING-level message
- **THEN** the watcher SHALL remove the stale timer entry for that file path
- **THEN** the watcher SHALL NOT call `ingest_path_async()`

#### Scenario: Hash cache exceeds size cap
- **WHEN** the hash cache exceeds the maximum number of entries (default 50 000)
- **THEN** the watcher SHALL evict the least-recently-inserted entry before adding a new one
- **THEN** the evicted file SHALL be re-hashed on its next `modified` event (equivalent to cold-start behaviour)

### Requirement: Ingestion via `ingest_path_async()`

When the watcher determines that a file needs ingestion, it SHALL call `ingest_path_async()` with the single file path as the argument, the routed collection name, and the collection's effective settings resolved from the composition root's profile resolver (no workers override, no progress callback). Before ingesting, the watcher SHALL validate that the resolved file path lies within the watched directory root. If the resolved path falls outside the watch root (e.g., via a symlink to an external directory), the watcher SHALL log a WARNING and skip ingestion.

The `ingest_path_async()` function SHALL include an `error_type` field in all error return dicts (`"file"` for path/extension errors, `"connection"` for embedding connectivity failures, `"embedding"` for non-connection embedding failures). When all files fail during processing, the return dict SHALL include both `error_type` and `message` fields describing the failure.

#### Scenario: Single-file ingestion on event
- **WHEN** the watcher decides to ingest a file
- **THEN** the watcher SHALL validate the resolved path is within the watch root
- **THEN** the watcher SHALL call `ingest_path_async()` with that file's path
- **THEN** the watcher SHALL log the outcome (success with chunk count, or failure) to stderr at INFO level

#### Scenario: Symlink traversal blocked
- **WHEN** a file event fires for a symlink that points to a file outside the watched directory root
- **THEN** the watcher SHALL NOT call `ingest_path_async()` for that file
- **THEN** the watcher SHALL log a WARNING-level message indicating the path traversal was blocked
- **THEN** the watcher SHALL clean up the timer entry for that file path

#### Scenario: Correct file inside watch root
- **WHEN** a file event fires for a resolved path that is within the watched directory root
- **THEN** the watcher SHALL proceed with ingestion normally

### Requirement: Graceful shutdown

The watcher SHALL handle SIGINT (Ctrl+C) with a watcher-owned shutdown sequence. It SHALL NOT rely on `_shutdown_requested` as its primary shutdown mechanism (because `ingest_path_async()` unconditionally clears it). The shutdown sequence SHALL be: (1) cancel all pending `threading.Timer` callbacks to prevent new `ingest_path_async()` calls, (2) wait for any in-flight `ingest_path_async()` to complete naturally, with a **maximum wait of 30 seconds** — if ingestion has not completed, log a WARNING with the number of callbacks that remain in flight and stop waiting, (3) set `_shutdown_requested` as belt-and-suspenders for those callbacks, (4) stop the watchdog `Observer`, and (5) let the command return with status 0. The current daemon-timer implementation cannot synchronously cancel an in-flight async pipeline; a callback still running after the deadline may be abandoned when the process exits.

#### Scenario: Ctrl+C stops the watcher
- **WHEN** the user presses Ctrl+C while the watcher is running and no ingestion is in progress
- **THEN** the watcher SHALL cancel all pending debounce timers
- **THEN** the watcher SHALL stop the observer
- **THEN** the watcher SHALL log a shutdown message to stderr and exit with status 0

#### Scenario: Ctrl+C during in-flight ingestion
- **WHEN** the user presses Ctrl+C while an `ingest_path_async()` call is in progress
- **THEN** the watcher SHALL allow the in-flight ingestion to complete before stopping the observer, up to a 30-second maximum
- **THEN** the watcher SHALL NOT start new ingestions (all pending timers cancelled)
- **THEN** the watcher SHALL exit with status 0 after the in-flight ingestion finishes

#### Scenario: Ctrl+C during hung ingestion
- **WHEN** the user presses Ctrl+C while an `ingest_path_async()` call is in progress and the ingestion does not complete within 30 seconds
- **THEN** the watcher SHALL log a WARNING with the number of abandoned in-flight ingestions
- **THEN** the watcher SHALL stop waiting, set the shutdown flag, stop the observer, and let the command return with status 0
- **AND** the still-running daemon callback MAY be abandoned when the process exits

#### Scenario: Ctrl+C during debounce window
- **WHEN** the user presses Ctrl+C while a debounce timer is pending for a file
- **THEN** the watcher SHALL cancel the pending timer
- **THEN** the watcher SHALL NOT ingest the file
- **THEN** the watcher SHALL stop the observer and exit

### Requirement: Logging

The watcher SHALL log significant events to stderr at appropriate log levels:
- INFO: ingestion start, success with chunk count, shutdown, successful deletion with chunk count (e.g. `"Auto-removed paper.pdf — 8 chunk(s) deleted"`)
- WARNING: ingestion failure (except `FileNotFoundError` — see below), unexpected file system errors, path traversal blocked, file size limit exceeded, OSError during hashing, shutdown timeout with abandoned ingestions, failed deletion attempt (e.g. vector-store error, collection not found)
- CRITICAL: N consecutive `ConnectionError` failures (default 5), as reported by `ingest_path_async()` via `error_type: "connection"`. Failures with `error_type: "file"` or `error_type: "embedding"` SHALL NOT increment the consecutive-`ConnectionError` counter.
- DEBUG: skipped files (unsupported extension, unchanged hash), debounce timer resets, file-not-found-during-debounce, cancelled pending timers or cleared hash cache entries due to deletion

#### Scenario: Watch logs to stderr
- **WHEN** a file is successfully ingested
- **THEN** the watcher SHALL output an INFO-level log like `Auto-ingested <filename> — <N> chunk(s)`

#### Scenario: Logs ingestion failure
- **WHEN** `ingest_path_async()` fails with an error (e.g. corrupt PDF, vector-store issue)
- **THEN** the watcher SHALL log a WARNING-level message with the filename and error details

#### Scenario: Embedding failure does not trigger ConnectionError alert
- **WHEN** `ingest_path_async()` returns `error_type: "embedding"` (non-connection failure)
- **THEN** the watcher SHALL log the failure at WARNING level
- **THEN** the watcher SHALL NOT increment the consecutive-`ConnectionError` counter

### Requirement: Ingestion failure handling

When `ingest_path_async()` fails for a file, the watcher SHALL NOT update the cached hash, so the next `modified` event for that file triggers a fresh attempt. The watcher SHALL track consecutive failures using a thread-safe counter protected by a `threading.Lock`. If the last 5 consecutive failures are all `ConnectionError` (as indicated by `error_type: "connection"` from `ingest_path_async()`), the watcher SHALL log a CRITICAL-level message recommending the user check Ollama and restart the watcher. Failures with other `error_type` values SHALL NOT count toward the `ConnectionError` threshold. Autonomous retry loops SHALL NOT be implemented in v1.

#### Scenario: File ingestion failure keeps hash unchanged
- **WHEN** `ingest_path_async()` fails for a file (e.g. corrupt PDF)
- **THEN** the watcher SHALL NOT update the file's cached hash
- **THEN** a subsequent `modified` event for the same file SHALL trigger a fresh ingestion attempt

#### Scenario: Consecutive ConnectionError triggers critical alert
- **WHEN** the watcher experiences 5 consecutive failures with `error_type: "connection"`
- **THEN** the watcher SHALL log a CRITICAL-level message indicating Ollama may be unreachable
- **THEN** the watcher SHALL continue running (not auto-exit) so it can recover when Ollama restarts

#### Scenario: Embedding failure resets ConnectionError counter
- **WHEN** the watcher has accumulated 3 consecutive `ConnectionError` failures
- **AND** the next ingestion fails with `error_type: "embedding"` (not `"connection"`)
- **THEN** the watcher SHALL log a WARNING (not CRITICAL) for the embedding failure
- **THEN** the consecutive-`ConnectionError` counter SHALL be reset to 0

#### Scenario: File deleted during debounce window
- **WHEN** a file event triggers a debounce timer, but the file is deleted before the timer fires
- **THEN** the watcher SHALL catch the resulting `FileNotFoundError` from `ingest_path_async()`
- **THEN** the watcher SHALL log a DEBUG-level message (not WARNING — it's a normal race condition)
- **THEN** the watcher SHALL remove the file's entry from the hash cache and pending timer tracking

### Requirement: Ingestion throttling

To limit active ingestion under batch file events (e.g. copying hundreds of files into the watched directory), the watcher SHALL limit concurrent calls to `ingest_path_async()` using a `threading.BoundedSemaphore(2)`. The semaphore ensures at most 2 ingestions run simultaneously. Each file still owns a daemon `threading.Timer`; callbacks waiting on the semaphore are therefore pending threads, not a bounded work queue.

#### Scenario: Batch file creation is throttled
- **WHEN** 100 supported files are created simultaneously in the watched directory
- **THEN** the watcher SHALL NOT call `ingest_path_async()` for more than 2 files concurrently
- **THEN** remaining files SHALL be ingested as the semaphore permits

### Requirement: Installed login watchers preserve watch command semantics

A watcher started by the login watcher installer SHALL invoke the existing `rag-mcp watch` command and SHALL preserve the watch command's collection routing, debounce, recursive filtering, deletion handling, logging, and graceful shutdown semantics.

#### Scenario: Installed watcher routes to selected collection
- **WHEN** a LaunchAgent generated by `install-login-watcher` starts for collection `research`
- **THEN** the launched process SHALL run `rag-mcp watch` with `--collection research`
- **THEN** created, modified, and deleted files SHALL affect the `research` collection according to the existing watch-command requirements

#### Scenario: Installed watcher uses selected debounce
- **WHEN** a LaunchAgent generated by `install-login-watcher` starts with debounce `5`
- **THEN** the launched process SHALL run `rag-mcp watch` with `--debounce 5`
- **THEN** file events SHALL be debounced according to the existing watch-command requirements

### Requirement: A moved source leaves no orphaned chunks

Handling a move SHALL leave the index consistent with the filesystem: the
source's content SHALL be indexed exactly once, under its current path.

#### Scenario: No duplicate content after a move

- **GIVEN** a watched file indexed at path A
- **WHEN** it is moved to path B inside the watch tree
- **AND** the watcher has processed the event
- **THEN** the collection SHALL contain chunks for B
- **AND** SHALL contain no chunks for A

#### Scenario: Move out of the watch tree removes chunks

- **GIVEN** a watched file indexed at path A
- **WHEN** it is moved to a destination outside the watch tree
- **THEN** the chunks for A SHALL be removed
- **AND** no ingest SHALL be attempted for the destination

#### Scenario: Move into the watch tree ingests

- **GIVEN** a supported file outside the watch tree
- **WHEN** it is moved to a path inside the watch tree
- **THEN** it SHALL be ingested under its new path

#### Scenario: Move of an unindexed file is a no-op

- **GIVEN** a supported file inside the watch tree that was never ingested
- **WHEN** it is moved
- **THEN** the removal step SHALL report zero chunks removed
- **AND** SHALL NOT raise

### Requirement: A move does not fork the index after cleanup failure

Destination ingestion SHALL be conditional on successful cleanup of the old
path. A failed cleanup SHALL be reported and retried or left pending; it SHALL
NOT be treated as success.

#### Scenario: Old-path cleanup fails

- **GIVEN** a watched file indexed at path A
- **WHEN** it is moved to path B and deletion of A fails
- **THEN** B SHALL NOT be ingested as though the move completed
- **AND** the failure SHALL be observable and eligible for retry

