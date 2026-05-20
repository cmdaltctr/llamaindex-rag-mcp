# Delta Specification: watch-command

## MODIFIED Requirements

### Requirement: CLI subcommand `rag-mcp watch`

The system SHALL provide a `rag-mcp watch <path>` CLI subcommand that monitors a directory tree for supported document files and auto-ingests them into the ChromaDB index using the existing `ingest_path()` pipeline. The subcommand SHALL accept an optional `--collection TEXT` flag (default `"documents"`) that routes auto-ingested files to a specific ChromaDB collection.

#### Scenario: Basic watch starts and waits
- **WHEN** the user runs `rag-mcp watch /path/to/docs`
- **THEN** the process SHALL block and monitor `/path/to/docs` for file system events
- **THEN** the process SHALL output a message like `Watching /path/to/docs for document changes…` to stderr

#### Scenario: Watch rejects non-existent path
- **WHEN** the user runs `rag-mcp watch /nonexistent/path`
- **THEN** the process SHALL print an error message to stderr and exit with a non-zero status code

#### Scenario: Watch with collection flag
- **WHEN** the user runs `rag-mcp watch /path/to/docs --collection research`
- **THEN** auto-ingested files SHALL be stored in the `"research"` ChromaDB collection
- **THEN** the startup message SHALL include the collection name

#### Scenario: Watch without collection flag uses default
- **WHEN** the user runs `rag-mcp watch /path/to/docs` without `--collection`
- **THEN** auto-ingested files SHALL be stored in the default `"documents"` ChromaDB collection

### Requirement: Ingestion via `ingest_path()`

When the watcher determines that a file needs ingestion, it SHALL call `ingestion.ingest_path()` with the single file path as the argument, using default chunking settings (no workers override, no progress callback). The watcher SHALL pass its configured `collection_name` to `ingest_path()`. Before ingesting, the watcher SHALL validate that the resolved file path lies within the watched directory root. If the resolved path falls outside the watch root (e.g., via a symlink to an external directory), the watcher SHALL log a WARNING and skip ingestion.

The `ingest_path()` function SHALL include an `error_type` field in all error return dicts (`"file"` for path/extension errors, `"connection"` for embedding connectivity failures, `"embedding"` for non-connection embedding failures). When all files fail during processing, the return dict SHALL include both `error_type` and `message` fields describing the failure.

#### Scenario: Single-file ingestion on event
- **WHEN** the watcher decides to ingest a file
- **THEN** the watcher SHALL validate the resolved path is within the watch root
- **THEN** the watcher SHALL call `ingest_path()` with that file's path and the configured `collection_name`
- **THEN** the watcher SHALL log the outcome (success with chunk count, or failure) to stderr at INFO level

#### Scenario: Symlink traversal blocked
- **WHEN** a file event fires for a symlink that points to a file outside the watched directory root
- **THEN** the watcher SHALL NOT call `ingest_path()` for that file
- **THEN** the watcher SHALL log a WARNING-level message indicating the path traversal was blocked
- **THEN** the watcher SHALL clean up the timer entry for that file path

#### Scenario: Correct file inside watch root
- **WHEN** a file event fires for a resolved path that is within the watched directory root
- **THEN** the watcher SHALL proceed with ingestion normally
