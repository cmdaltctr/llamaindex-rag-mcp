# Parallel Ingestion Capability Specification

## ADDED Requirements

### Requirement: Configurable embedding batch size

The system SHALL support a configurable `embed_batch_size` for Ollama embedding
calls, defaulting to 100 (increased from the current hardcoded 10).

#### Scenario: Default batch size is 100

- **GIVEN** the `EMBED_BATCH_SIZE` environment variable is not set
- **WHEN** ingestion is invoked (CLI or MCP)
- **THEN** the Ollama embedding model SHALL be configured with `embed_batch_size=100`

#### Scenario: Custom batch size via env var

- **GIVEN** `EMBED_BATCH_SIZE=50` is set in `.env`
- **WHEN** ingestion is invoked
- **THEN** the Ollama embedding model SHALL be configured with `embed_batch_size=50`

#### Scenario: Invalid batch size falls back to default

- **GIVEN** `EMBED_BATCH_SIZE=notanumber` is set in `.env`
- **WHEN** ingestion is invoked
- **THEN** the system SHALL emit a warning log
- **AND** fall back to the default of 100

### Requirement: Concurrent file-level reading and chunking

When `--workers > 1` (or `INGEST_WORKERS > 1`), the system SHALL use
`ThreadPoolExecutor` to read and chunk multiple files concurrently.

#### Scenario: Parallel file processing with 4 workers

- **GIVEN** a directory with 20 PDF files
- **WHEN** `rag-mcp ingest ./docs/ --workers 4` is invoked
- **THEN** up to 4 files SHALL be read and chunked concurrently
- **AND** all 20 files SHALL be processed

#### Scenario: Single-threaded fallback

- **GIVEN** `--workers` is not specified and `INGEST_WORKERS` is not set
- **WHEN** `rag-mcp ingest ./docs/` is invoked
- **THEN** file processing SHALL use the default worker count (4)

#### Scenario: Workers clamped to minimum 1

- **GIVEN** `--workers 0` or `--workers -5` is specified
- **WHEN** `rag-mcp ingest ./docs/` is invoked
- **THEN** the worker count SHALL be clamped to 1 (single-threaded)

#### Scenario: Parallel ingestion produces same chunks as sequential

- **GIVEN** a directory with 5 PDF files
- **WHEN** the same files are ingested first with `--workers 1` and then with `--workers 4`
- **THEN** the total chunk count SHALL be identical in both cases

### Requirement: Serialised ChromaDB writes

When parallel file processing is active, all ChromaDB vector store writes SHALL
be serialised to prevent SQLite lock contention and data corruption.

#### Scenario: Parallel reads, serial write

- **GIVEN** ingestion is running with `--workers 4`
- **WHEN** file reading and chunking completes (Phase 1)
- **THEN** a single ChromaDB `collection.add()` call SHALL be made with all nodes (Phase 2)

#### Scenario: Single-threaded mode uses existing flow

- **GIVEN** ingestion is running with `--workers 1` (single-threaded)
- **WHEN** a file is ingested
- **THEN** the existing `VectorStoreIndex(nodes, storage_context=storage_context)` flow SHALL be used
- **AND** no lock SHALL be acquired

### Requirement: Ollama embedding concurrency gate

The system SHALL gate concurrent Ollama embedding API calls behind a
`threading.BoundedSemaphore` to prevent overwhelming the local Ollama service.

#### Scenario: Gate limits concurrent embed calls

- **GIVEN** `EMBED_CONCURRENCY=2` is set
- **AND** 4 worker threads are processing files
- **WHEN** workers attempt to call Ollama for embedding simultaneously
- **THEN** at most 2 threads SHALL be executing embedding requests at any time
- **AND** remaining threads SHALL block until a permit is released

#### Scenario: Gate default is 2

- **GIVEN** `EMBED_CONCURRENCY` is not set
- **WHEN** ingestion is invoked with parallel workers
- **THEN** the BoundedSemaphore SHALL be initialised with value 2

### Requirement: Graceful SIGINT handling

The system SHALL handle `SIGINT` (Ctrl+C) gracefully during ingestion, ensuring
no partial or corrupted data is left in the ChromaDB collection.

#### Scenario: Ctrl+C during parallel file reading

- **GIVEN** ingestion is processing files with `--workers 4`
- **WHEN** the user presses Ctrl+C
- **THEN** the signal handler SHALL set a shutdown flag
- **AND** workers SHALL finish their current file, then stop
- **AND** no partial chunks SHALL be written to ChromaDB
- **AND** a message "Ingestion interrupted" SHALL be printed

#### Scenario: Ctrl+C during embedding phase

- **GIVEN** file processing is complete and embedding is in progress
- **WHEN** the user presses Ctrl+C
- **THEN** the system SHALL abort the embedding call
- **AND** no partial vector data SHALL be written to ChromaDB
- **AND** the ChromaDB collection SHALL remain in its previous consistent state

### Requirement: Progress reporting

The system SHALL display Rich-powered progress bars during ingestion showing
files processed, chunks embedded, elapsed time, and estimated time remaining.

#### Scenario: Progress bars during ingestion

- **GIVEN** a directory with 10 PDF files
- **WHEN** `rag-mcp ingest ./docs/` is invoked
- **THEN** a progress bar SHALL be displayed showing file reading progress
- **AND** a second progress bar SHALL be displayed showing embedding progress
- **AND** elapsed time SHALL be shown
- **AND** estimated time remaining (ETA) SHALL be shown after sufficient samples

#### Scenario: Progress reporting in non-TTY mode

- **GIVEN** stdout is not a terminal (e.g., piped to a file)
- **WHEN** `rag-mcp ingest ./docs/` is invoked
- **THEN** plain-text progress lines SHALL be printed (e.g., "Processing file 7/10 (70%)")
- **AND** no ANSI escape codes or animated bars SHALL be emitted

### Requirement: Error resilience — per-file failure isolation

When processing multiple files, a failure in one file SHALL NOT prevent
remaining files from being processed.

#### Scenario: Corrupt file skipped

- **GIVEN** a directory with 3 PDFs, one of which is corrupt
- **WHEN** `rag-mcp ingest ./docs/` is invoked
- **THEN** the two valid PDFs SHALL be indexed
- **AND** the corrupt file SHALL be logged as a warning
- **AND** the final summary SHALL report "2 files indexed, 1 skipped"

#### Scenario: All files fail

- **GIVEN** a directory where every file is corrupted or unreadable
- **WHEN** `rag-mcp ingest ./docs/` is invoked
- **THEN** the exit code SHALL be non-zero
- **AND** a summary SHALL report "0 files indexed, N skipped"

## MODIFIED Requirements

### Requirement: embed_batch_size is configurable (was hardcoded 10)

The `Settings.embed_model` configuration in `config.py` SHALL use the `EMBED_BATCH_SIZE`
environment variable instead of a hardcoded value of 10.

#### Scenario: Existing behaviour preserved when env var not set

- **GIVEN** `EMBED_BATCH_SIZE` is not set in `.env`
- **WHEN** the MCP server or CLI starts
- **THEN** `embed_batch_size` SHALL default to 100
- **AND** this change SHALL be transparent to existing MCP tool callers

## REMOVED Requirements

_None._
