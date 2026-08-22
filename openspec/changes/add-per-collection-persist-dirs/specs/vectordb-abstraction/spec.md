## MODIFIED Requirements

### Requirement: ChromaDB as first implementation

The system SHALL provide `core/vectordb/chroma.py` implementing the
`VectorStore` ABC, absorbing all logic from `chroma_utils.py` and the
ChromaDB-specific collection management formerly in the ingestion writer.
`chroma_utils.py` SHALL cease to exist as a top-level module.
`core/vectordb/chroma.py` SHALL be the **only** module in the package that
imports `chromadb` or constructs a ChromaDB client; every other consumer,
including the codebase map, SHALL go through the `VectorStore` interface.

#### Scenario: Single chromadb import site

- **WHEN** `src/rag_mcp/` is searched for `import chromadb` or
  `chromadb.PersistentClient`
- **THEN** the only match MUST be in `core/vectordb/chroma.py`

#### Scenario: Codebase map goes through the interface

- **WHEN** the codebase map needs indexed-document information
- **THEN** it MUST call `VectorStore` methods on an injected store
- **AND** it MUST NOT create its own ChromaDB client or persist directory
  handle

#### Scenario: Existing collections keep working

- **WHEN** the server starts against an existing flat `chroma_persist_dir`
  (default `./chroma_db`) containing collections in the pre-change layout
- **THEN** all previously indexed collections MUST be readable and queryable
  after the documented storage-layout migration defined by the
  `collection-storage-layout` capability, which MUST preserve stored
  embeddings, or after an equivalent re-ingest, which recomputes them

#### Scenario: Existing tests pass against the implementation

- **WHEN** `uv run pytest -m "not slow" --cov=rag_mcp` runs
- **THEN** all pre-existing tests MUST pass against the ChromaDB-backed
  implementation with no assertion changes beyond injected-settings plumbing

---

### Requirement: Store selection via configuration

The system SHALL select the vector store implementation via a
`VECTOR_STORE` environment variable defaulting to `chroma`, read from
`config/` and constructed in `compose.py`. The constructed store SHALL be
passed to consumers by injection, including to the codebase map subsystem
under `core/codebase/`. The store's persist directory SHALL be resolved per
collection by the composition root according to the
`collection-storage-layout` capability before construction; the store
implementation SHALL NOT independently read a flat global persist-directory
default to decide where to place data.

#### Scenario: Default store is resolved from configuration

- **WHEN** `VECTOR_STORE` is not set
- **THEN** `compose.py` MUST construct the configured default vector-store
  implementation through the registry

#### Scenario: Unknown store value

- **WHEN** `VECTOR_STORE` names an implementation with no registered
  implementation
- **THEN** the system MUST fail at startup with a clear error listing
  available implementations

#### Scenario: Store is injected into every consumer

- **WHEN** an operation or subsystem needs vector store access
- **THEN** it MUST receive the store as a parameter or constructor argument
- **AND** it MUST NOT construct one itself

#### Scenario: Alternate store is selectable by configuration

- **WHEN** `VECTOR_STORE` names a registered non-default implementation,
  for example `lancedb`
- **THEN** `compose.py` MUST resolve and construct that implementation
  through the registry
- **AND** every consumer MUST receive it by injection through the same
  paths that receive the default store

#### Scenario: Access before composition

- **GIVEN** no vector store has been composed or injected
- **WHEN** a core consumer requests process-wide store access
- **THEN** the accessor MUST fail clearly rather than construct a default

#### Scenario: Persist directory arrives resolved

- **WHEN** the composition root constructs the store for an operation on a
  collection
- **THEN** the persist directory SHALL already be resolved from the
  collection-storage-layout rules
- **AND** the store SHALL reject a missing injected directory and MUST NOT
  consult a global flat default during any production client access
