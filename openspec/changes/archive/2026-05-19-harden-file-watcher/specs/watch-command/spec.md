# Delta Specification: watch-command

## ADDED Requirements

### Requirement: File size limit

The watcher SHALL reject files larger than a configurable maximum size (default 500 MB) before hashing. If a file exceeds the limit, the watcher SHALL log a WARNING-level message and skip ingestion. This prevents resource exhaustion (CPU, memory) from attempting to hash and embed multi-gigabyte files in the watched directory.

#### Scenario: Large file rejected before hashing
- **WHEN** a `modified` event fires for a supported file larger than 500 MB
- **THEN** the watcher SHALL NOT compute its SHA-256 hash
- **THEN** the watcher SHALL log a WARNING-level message indicating the file exceeds the maximum size
- **THEN** the watcher SHALL NOT call `ingest_path()` for that file

#### Scenario: Normal-sized file proceeds
- **WHEN** a `modified` event fires for a supported file under the size limit
- **THEN** the watcher SHALL proceed with hashing and ingestion as normal

## MODIFIED Requirements

### Requirement: Graceful shutdown

The watcher SHALL handle SIGINT (Ctrl+C) with a watcher-owned shutdown sequence. It SHALL NOT rely on `_shutdown_requested` as its primary shutdown mechanism (because `ingest_path()` unconditionally clears it). The shutdown sequence SHALL be: (1) cancel all pending `threading.Timer` callbacks to prevent new `ingest_path()` calls, (2) wait for any in-flight `ingest_path()` to complete naturally, with a **maximum wait of 30 seconds** — if in-flight ingestion has not completed within 30 seconds, the watcher SHALL log a WARNING with the number of abandoned in-flight ingestions and force-stop, (3) set `_shutdown_requested` as belt-and-suspenders for the in-flight call, (4) stop the watchdog `Observer`, (5) exit cleanly with status 0.

#### Scenario: Ctrl+C stops the watcher
- **WHEN** the user presses Ctrl+C while the watcher is running and no ingestion is in progress
- **THEN** the watcher SHALL cancel all pending debounce timers
- **THEN** the watcher SHALL stop the observer
- **THEN** the watcher SHALL log a shutdown message to stderr and exit with status 0

#### Scenario: Ctrl+C during in-flight ingestion
- **WHEN** the user presses Ctrl+C while an `ingest_path()` call is in progress
- **THEN** the watcher SHALL allow the in-flight ingestion to complete before stopping the observer, up to a 30-second maximum
- **THEN** the watcher SHALL NOT start new ingestions (all pending timers cancelled)
- **THEN** the watcher SHALL exit with status 0 after the in-flight ingestion finishes

#### Scenario: Ctrl+C during hung ingestion
- **WHEN** the user presses Ctrl+C while an `ingest_path()` call is in progress and the ingestion does not complete within 30 seconds
- **THEN** the watcher SHALL log a WARNING with the number of abandoned in-flight ingestions
- **THEN** the watcher SHALL force-stop (cancel timers, stop observer, exit 0)

#### Scenario: Ctrl+C during debounce window
- **WHEN** the user presses Ctrl+C while a debounce timer is pending for a file
- **THEN** the watcher SHALL cancel the pending timer
- **THEN** the watcher SHALL NOT ingest the file
- **THEN** the watcher SHALL stop the observer and exit

### Requirement: Ingestion via `ingest_path()`

When the watcher determines that a file needs ingestion, it SHALL call `ingestion.ingest_path()` with the single file path as the argument, using default chunking settings (no workers override, no progress callback). Before ingesting, the watcher SHALL validate that the resolved file path lies within the watched directory root. If the resolved path falls outside the watch root (e.g., via a symlink to an external directory), the watcher SHALL log a WARNING and skip ingestion.

The `ingest_path()` function SHALL include an `error_type` field in all error return dicts (`"file"` for path/extension errors, `"connection"` for embedding connectivity failures, `"embedding"` for non-connection embedding failures). When all files fail during processing, the return dict SHALL include both `error_type` and `message` fields describing the failure.

#### Scenario: Single-file ingestion on event
- **WHEN** the watcher decides to ingest a file
- **THEN** the watcher SHALL validate the resolved path is within the watch root
- **THEN** the watcher SHALL call `ingest_path()` with that file's path
- **THEN** the watcher SHALL log the outcome (success with chunk count, or failure) to stderr at INFO level

#### Scenario: Symlink traversal blocked
- **WHEN** a file event fires for a symlink that points to a file outside the watched directory root
- **THEN** the watcher SHALL NOT call `ingest_path()` for that file
- **THEN** the watcher SHALL log a WARNING-level message indicating the path traversal was blocked
- **THEN** the watcher SHALL clean up the timer entry for that file path

#### Scenario: Correct file inside watch root
- **WHEN** a file event fires for a resolved path that is within the watched directory root
- **THEN** the watcher SHALL proceed with ingestion normally

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
- **THEN** the watcher SHALL NOT call `ingest_path()`

#### Scenario: Hash cache exceeds size cap
- **WHEN** the hash cache exceeds the maximum number of entries (default 50 000)
- **THEN** the watcher SHALL evict the least-recently-inserted entry before adding a new one
- **THEN** the evicted file SHALL be re-hashed on its next `modified` event (equivalent to cold-start behaviour)

### Requirement: Logging

The watcher SHALL log significant events to stderr at appropriate log levels:
- INFO: ingestion start, success with chunk count, shutdown
- WARNING: ingestion failure (except `FileNotFoundError` — see below), unexpected file system errors, path traversal blocked, file size limit exceeded, OSError during hashing, shutdown timeout with abandoned ingestions
- CRITICAL: N consecutive `ConnectionError` failures (default 5), as reported by `ingest_path()` via `error_type: "connection"`. Failures with `error_type: "file"` or `error_type: "embedding"` SHALL NOT increment the consecutive-`ConnectionError` counter.
- DEBUG: skipped files (unsupported extension, unchanged hash), debounce timer resets, file-not-found-during-debounce

#### Scenario: Watch logs to stderr
- **WHEN** a file is successfully ingested
- **THEN** the watcher SHALL output an INFO-level log like `Auto-ingested <filename> — <N> chunk(s)`

#### Scenario: Logs ingestion failure
- **WHEN** `ingest_path()` fails with an error (e.g. corrupt PDF, ChromaDB issue)
- **THEN** the watcher SHALL log a WARNING-level message with the filename and error details

#### Scenario: Embedding failure does not trigger ConnectionError alert
- **WHEN** `ingest_path()` returns `error_type: "embedding"` (non-connection failure)
- **THEN** the watcher SHALL log the failure at WARNING level
- **THEN** the watcher SHALL NOT increment the consecutive-`ConnectionError` counter

### Requirement: Ingestion failure handling

When `ingest_path()` fails for a file, the watcher SHALL NOT update the cached hash, so the next `modified` event for that file triggers a fresh attempt. The watcher SHALL track consecutive failures using a thread-safe counter protected by a `threading.Lock`. If the last 5 consecutive failures are all `ConnectionError` (as indicated by `error_type: "connection"` from `ingest_path()`), the watcher SHALL log a CRITICAL-level message recommending the user check Ollama and restart the watcher. Failures with other `error_type` values SHALL NOT count toward the `ConnectionError` threshold. Autonomous retry loops SHALL NOT be implemented in v1.

#### Scenario: File ingestion failure keeps hash unchanged
- **WHEN** `ingest_path()` fails for a file (e.g. corrupt PDF)
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
- **THEN** the watcher SHALL catch the resulting `FileNotFoundError` from `ingest_path()`
- **THEN** the watcher SHALL log a DEBUG-level message (not WARNING — it's a normal race condition)
- **THEN** the watcher SHALL remove the file's entry from the hash cache and pending timer tracking
