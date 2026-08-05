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

- **WHEN** the server starts against existing `output/chroma_*` data
- **THEN** all previously indexed collections MUST be readable and queryable
  with no data migration

#### Scenario: Existing tests pass against the implementation

- **WHEN** `uv run pytest -m "not slow" --cov=rag_mcp` runs
- **THEN** all pre-existing tests MUST pass against the ChromaDB-backed
  implementation with no assertion changes beyond injected-settings plumbing

---

### Requirement: Store selection via configuration

The system SHALL select the vector store implementation via a
`VECTOR_STORE` environment variable defaulting to `chroma`, resolved through
`config.py` and constructed in `compose.py`. The constructed store SHALL be
passed to consumers by injection, including to the codebase map subsystem
under `core/codebase/`.

#### Scenario: Default is chroma

- **WHEN** `VECTOR_STORE` is not set
- **THEN** `compose.py` MUST construct the ChromaDB implementation

#### Scenario: Unknown store value

- **WHEN** `VECTOR_STORE` names an implementation with no registered
  implementation
- **THEN** the system MUST fail at startup with a clear error listing
  available implementations

#### Scenario: Store is injected into every consumer

- **WHEN** an operation or subsystem needs vector store access
- **THEN** it MUST receive the store as a parameter or constructor argument
- **AND** it MUST NOT construct one itself
