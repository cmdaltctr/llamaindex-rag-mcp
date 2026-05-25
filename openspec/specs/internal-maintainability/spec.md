# internal-maintainability Specification

## Purpose

Define internal code-quality boundaries for helper naming, lock naming, test isolation, and concurrency primitives so the codebase remains honest and auditable without changing user-facing behaviour.

## Requirements
### Requirement: Unsupported file discovery comments match behavior
Internal file discovery helpers SHALL not contain unreachable branches or comments claiming unsupported single files are tracked when callers reject unsupported single files earlier.

#### Scenario: Unsupported single file handling remains explicit
- **WHEN** `ingest_path_async()` receives a single file with an unsupported extension
- **THEN** it SHALL return an error explaining the unsupported extension
- **THEN** `_gather_supported_files()` SHALL not contain misleading unreachable logic for that case

### Requirement: Benchmark chunking helper boundary is explicit
The benchmark command SHALL use a chunking helper whose intended internal/public boundary is explicit.

#### Scenario: Benchmark chunks a file without indexing it
- **WHEN** `rag-mcp benchmark --file path` runs
- **THEN** the command SHALL read and chunk the file without writing to ChromaDB
- **THEN** the helper used for read-and-chunk behavior SHALL be named or documented so maintainers know it is intentionally shared with benchmark

### Requirement: Shared watcher state lock is clearly named
Watcher synchronization primitives SHALL be named according to the state they protect.

#### Scenario: Lock protects timer and hash-cache state
- **WHEN** a lock protects both pending timers and hash-cache cleanup
- **THEN** its name SHALL reflect shared watcher state rather than only timers
- **THEN** watcher behavior SHALL remain unchanged

### Requirement: Metadata ChromaDB client lazy initialization is safe
The metadata extraction ChromaDB client cache SHALL avoid unguarded first-use races.

#### Scenario: Concurrent first category lookup
- **WHEN** two ingestion threads request existing categories at the same time
- **THEN** `_get_chroma_client()` SHALL initialize the cached client without unguarded double-creation
- **THEN** both callers SHALL receive a usable ChromaDB client

### Requirement: Test persist directory does not imply shared filesystem state
Tests SHALL not rely on a hardcoded shared ChromaDB persist path when an isolated path is available.

#### Scenario: Test environment isolation
- **WHEN** tests configure `CHROMA_PERSIST_DIR`
- **THEN** the configured path SHALL be isolated per test run or ignored by a documented in-memory ChromaDB patch
- **THEN** future readers SHALL not infer that tests write to a shared `/tmp` path
