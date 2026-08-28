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

### Requirement: Documented source paths resolve

Documentation that cites a source file path SHALL cite a path that exists.
Every `src/rag_mcp/**/*.py` path referenced in `docs/guides/` or
`tests/TEST_README.md` SHALL resolve to a file on disk. Records under
`docs/adr/` are EXCLUDED: an ADR legitimately cites paths that were correct
when the decision was taken and have since moved.

#### Scenario: A guide cites a path deleted by a refactor

- **WHEN** a guide references `src/rag_mcp/config.py` after the v2 split moved it to `src/rag_mcp/config/__init__.py`
- **THEN** the documentation reference check SHALL fail
- **THEN** the failure SHALL name the citing file, its line, and the unresolved path

#### Scenario: A historical ADR cites a since-deleted path

- **WHEN** `docs/adr/026-provider-registry-and-openrouter.md` references `src/rag_mcp/metadata_extractor.py`, a v1 module deleted in v2.0.0
- **THEN** the check SHALL NOT fail
- **THEN** the ADR SHALL remain unmodified, its accuracy carried by a dated forward note instead

### Requirement: Documented provider names match the live registries

The provider names listed in `docs/guides/providers.md` SHALL match the names
registered in the embedding and LLM provider registries exactly. The guide
SHALL delimit these names in a machine-readable block so the check reads a
declared list rather than inferring one from prose.

#### Scenario: A provider is added without updating the guide

- **WHEN** a new provider is registered in `core/providers/embeddings/registry.py` via `register()`
- **AND** `docs/guides/providers.md` is not updated to list it
- **THEN** the registry contract test SHALL fail
- **THEN** the failure SHALL name the provider present in the registry but absent from the guide

#### Scenario: The guide names a provider that no longer exists

- **WHEN** `docs/guides/providers.md` lists a provider name absent from `available()`
- **THEN** the registry contract test SHALL fail
- **THEN** the failure SHALL name the provider documented but unregistered

#### Scenario: Guide and registries agree

- **WHEN** the documented names equal `embed_registry.available()` for embeddings and `llm_registry.available()` for LLMs
- **THEN** the check SHALL pass without requiring any suppression or allowlist entry
