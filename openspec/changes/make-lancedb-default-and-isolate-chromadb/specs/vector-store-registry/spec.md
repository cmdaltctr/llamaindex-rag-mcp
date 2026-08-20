## ADDED Requirements

### Requirement: Default store construction SHALL use registry dispatch

Every construction path, including the process-wide lazy fallback, SHALL resolve the configured vector store through the registry. No fallback path SHALL import a concrete store unconditionally.

#### Scenario: Lazy default without prior composition

- **GIVEN** no process-wide store has been registered
- **WHEN** a core caller requests the default store
- **THEN** the configured store MUST be constructed through registry lookup
- **AND** the base default MUST resolve to LanceDB

### Requirement: Missing optional backends SHALL fail with installation guidance

A registered backend whose optional package is absent SHALL produce an actionable startup error. The error SHALL name the selected backend, required extra, and supported default without exposing credentials.

#### Scenario: Chroma selected without optional extra

- **GIVEN** `VECTOR_STORE=chroma`
- **AND** the `chroma` extra is not installed
- **WHEN** runtime setup resolves the registry entry
- **THEN** startup MUST fail before ingestion or retrieval
- **AND** the error MUST instruct the operator to install the `chroma` extra or select LanceDB

#### Scenario: Broken optional backend installation

- **GIVEN** an optional backend package is present but its registered factory cannot import
- **WHEN** registry resolution occurs
- **THEN** the error MUST distinguish a broken installation from an absent extra
- **AND** it MUST retain the original exception as diagnostic context

### Requirement: Missing Chroma SHALL not break LanceDB capabilities

A base installation SHALL support LanceDB ingestion, retrieval, hybrid BM25, profiles, deletion, and runtime summaries without importing Chroma-specific capability probes.

#### Scenario: Native sparse requested without Chroma

- **GIVEN** the base LanceDB installation has no Chroma extra
- **AND** a Chroma-only native sparse mode is requested
- **WHEN** sparse capability is resolved
- **THEN** the system MUST fall back to BM25 with an actionable warning
- **AND** it MUST NOT fail from a missing Chroma import
