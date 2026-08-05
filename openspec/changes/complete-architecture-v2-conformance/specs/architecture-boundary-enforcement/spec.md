## ADDED Requirements

### Requirement: ChromaDB confined to the vector store implementation

Production code SHALL import `chromadb` only from
`src/rag_mcp/core/vectordb/chroma.py`. Every other module that needs vector
store access SHALL receive a `VectorStore` instance by injection. An
import-linter contract SHALL enforce this, and SHALL fail CI when any other
module imports `chromadb`.

#### Scenario: Codebase map uses the injected store

- **WHEN** the codebase map builds its file-type index
- **THEN** it MUST obtain document data through the injected `VectorStore`
- **AND** it MUST NOT call `chromadb.PersistentClient(...)` directly

#### Scenario: Contract fails on a new leak

- **WHEN** a module outside `core/vectordb/chroma.py` adds `import chromadb`
- **THEN** `uv run lint-imports` MUST fail naming the offending module

---

### Requirement: Configuration is a leaf module

`rag_mcp.config` SHALL NOT import from `rag_mcp.core` business logic,
`rag_mcp.compose`, `rag_mcp.transports`, `rag_mcp.integrations`, or
`rag_mcp.daemon`. The only sanctioned upward references are the pure-data
subpackage settings models (`rag_mcp.core.*.settings`). Runtime capability
probing (sparse backend availability, PDF reader availability) SHALL live in
`compose.py`, not in `config`. An import-linter contract SHALL enforce this.

#### Scenario: No business-logic import in config

- **WHEN** `src/rag_mcp/config/__init__.py` is inspected
- **THEN** it MUST NOT import `_detect_native_sparse_capability` or any other
  symbol from `rag_mcp.core.retrieval`, `rag_mcp.core.ingestion`,
  `rag_mcp.core.metadata`, or `rag_mcp.core.vectordb`

#### Scenario: Capability probing lives in the composition root

- **WHEN** the effective sparse backend or PDF reader is resolved
- **THEN** the probe MUST execute in `compose.py`
- **AND** `config` MUST expose only the declared preference value

#### Scenario: Contract fails on a new upward import

- **WHEN** a developer adds an import from `rag_mcp.config` to any `core/`
  module other than a `settings` model
- **THEN** `uv run lint-imports` MUST fail

---

### Requirement: Integrations are acyclic leaves

Modules under `src/rag_mcp/integrations/` SHALL NOT import from
`rag_mcp.core`, `rag_mcp.transports`, or `rag_mcp.daemon`. No module SHALL
import another module solely to preserve a test monkeypatch target. An
import-linter contract SHALL enforce the direction.

#### Scenario: Magika has no back-reference

- **WHEN** `src/rag_mcp/integrations/magika.py` is inspected
- **THEN** it MUST NOT import `rag_mcp.codebase_map` or
  `rag_mcp.core.codebase.codebase_map` in any form

#### Scenario: Availability probe is patched at its own module

- **WHEN** a test needs to simulate Magika being unavailable
- **THEN** it MUST patch the probe on `rag_mcp.integrations.magika`
- **AND** the codebase map MUST observe the patched result through its normal
  call into that module

---

### Requirement: Full-package import boundary coverage

The import-linter contract set SHALL cover every package under
`src/rag_mcp/`, not a subset. The business-layer contract SHALL name
`core.ingestion`, `core.retrieval`, `core.metadata`, `core.chunking`,
`core.vectordb`, `core.profiles`, `core.codebase`, `core.documents`, and
`daemon` as source modules, forbidding imports of `core.providers` and
`transports` from all of them.

#### Scenario: Every package is a contract source

- **WHEN** the contract set in `pyproject.toml` is compared against the
  packages present under `src/rag_mcp/`
- **THEN** every package MUST appear as a source module in at least one
  contract

#### Scenario: Transport import from core fails

- **WHEN** any module under `core/` or `daemon/` imports from
  `rag_mcp.transports`
- **THEN** `uv run lint-imports` MUST fail

---

### Requirement: Use-case subsystems live under core

The codebase-understanding subsystem SHALL live at `core/codebase/`
(`codebase_map`, `code_graph` and their supporting modules) and the
document-graph subsystem SHALL live at `core/documents/` (`doc_graph` and its
supporting modules), per the agreed target tree. No module under `core/` SHALL
import from a top-level `src/rag_mcp/*.py` business module.

#### Scenario: Ingestion no longer reaches upward

- **WHEN** `core/ingestion/pipeline.py` needs file-type detection
- **THEN** it MUST import from `rag_mcp.core.codebase`
- **AND** MUST NOT import from a top-level `rag_mcp.codebase_map` module

#### Scenario: Top-level business modules are gone

- **WHEN** `src/rag_mcp/` is listed after the change
- **THEN** the only top-level modules MUST be `__init__.py`, `compose.py`, and
  the `config/` package

#### Scenario: Subsystems share only settings

- **WHEN** `core/codebase/` and `core/documents/` imports are inspected
- **THEN** neither MUST import from `core/ingestion/` or `core/retrieval/`
  other than through injected interfaces

---

### Requirement: Executable file-size ceiling

No Python file under `src/rag_mcp/` SHALL exceed 500 lines. This ceiling SHALL
be asserted by an automated test rather than by review convention, and the test
SHALL report every offending file with its line count.

#### Scenario: Ceiling holds across the package

- **WHEN** the file-size test runs against `src/rag_mcp/**/*.py`
- **THEN** it MUST pass with zero files over 500 lines

#### Scenario: Regression is caught

- **WHEN** a file grows past 500 lines
- **THEN** the test MUST fail naming that file and its line count
