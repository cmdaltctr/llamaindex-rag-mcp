# Delta Specification: watch-command

## ADDED Requirements

### Requirement: Auto-removal of vectors on file deletion

The watcher SHALL handle `on_deleted` events from the watchdog library. When a supported file is deleted from the watched directory tree, the watcher SHALL automatically remove all its chunks from ChromaDB by calling `remove_document()` on the event's `src_path`. The handler SHALL also cancel any pending ingest timer for the same file path and clear its hash cache entry. Deletion SHALL NOT be debounced — it SHALL fire immediately on the `on_deleted` event.

#### Scenario: File deletion removes vectors
- **WHEN** a supported file (e.g. `paper.pdf`) is deleted from a watched directory
- **THEN** the watcher SHALL detect the deletion via `on_deleted`
- **THEN** the watcher SHALL cancel any pending ingest timer for that file path
- **THEN** the watcher SHALL clear the file's hash cache entry
- **THEN** the watcher SHALL call `remove_document()` to delete all chunks for that file from ChromaDB
- **THEN** the watcher SHALL log the deletion outcome at INFO level

#### Scenario: File deletion with no indexed chunks
- **WHEN** a supported file is deleted from a watched directory, but it was never successfully ingested (no chunks in ChromaDB)
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
- **THEN** the watcher SHALL NOT call `ingest_path()` for the deleted file (timer was cancelled)

## MODIFIED Requirements

### Requirement: File event filtering

The watcher SHALL respond to `on_created`, `on_modified`, AND `on_deleted` file system events for files with supported extensions (`.pdf`, `.docx`, `.pptx`, `.txt`, `.md`, `.html`, `.csv` as defined by `SUPPORTED_EXTENSIONS` in `config.py`). The watcher SHALL ignore hidden files (names starting with `.`), temporary files (`~$*`, `*.tmp`, `*.part`), and `.git` directories.

**Change**: Added `on_deleted` to the list of handled event types.

### Requirement: Logging

In addition to existing log levels, the watcher SHALL log deletion events at:

- **INFO**: Successful deletion with chunk count (e.g. `"Auto-removed paper.pdf — 8 chunk(s) deleted"`)
- **WARNING**: Failed deletion attempt (e.g. ChromaDB error, collection not found)
- **DEBUG**: Cancelled pending timers or cleared hash cache entries due to deletion

**Change**: Added deletion-related log events to the logging requirement.
