## ADDED Requirements

### Requirement: LanceDB SHALL pass production-lifecycle qualification before becoming default

The default flip SHALL be blocked until a TDR-014-admissible LanceDB campaign
passes real ingestion, reopen, retrieval, mutation, identity and recovery gates
at the final pre-flip commit and lock.

#### Scenario: Qualification succeeds

- **WHEN** the LanceDB campaign completes
- **THEN** it MUST prove parse/chunk/embed/write, restart/reopen, dense query, BM25 hybrid query, filters, unchanged re-ingest, replacement, deletion, identity, generations and interrupted-write recovery
- **AND** requested/effective backend, URI/index identity, score kind, embedding identity and raw operation rows MUST be retained

#### Scenario: Qualification is incomplete or fails

- **WHEN** any required lifecycle cell fails, is incomplete or is not evaluable
- **THEN** LanceDB MUST NOT become the executable default
- **AND** Stage 6 calibration MUST NOT treat it as the final baseline

### Requirement: Qualified LanceDB SHALL be the base-install vector-store default

After the qualification gate passes, the system SHALL resolve embedded LanceDB
when no explicit backend is supplied. The base path SHALL not import or require
ChromaDB.

#### Scenario: Unset selector in a clean base installation

- **GIVEN** qualification passed
- **AND** no recognised legacy Chroma data requires acknowledgement
- **AND** no backend is explicitly selected
- **WHEN** settings and composition complete
- **THEN** the effective store MUST be embedded LanceDB at `LANCEDB_URI`
- **AND** both Chroma distributions MUST be absent from the environment
- **AND** no Chroma module MUST be loaded

#### Scenario: Explicit LanceDB selection

- **GIVEN** `VECTOR_STORE=lancedb` is explicitly selected
- **WHEN** runtime setup completes
- **THEN** every ingestion, retrieval, profile and deletion operation MUST use the configured LanceDB store

### Requirement: Recognised legacy Chroma data SHALL require an explicit decision

Settings resolution SHALL retain whether the backend was explicitly supplied.
Recognised legacy Chroma data with no explicit choice SHALL stop startup before
ingestion or retrieval. The legacy directory SHALL remain untouched.

#### Scenario: Recognised legacy layout and no explicit backend

- **GIVEN** Chroma markers such as `chroma.sqlite3` or the documented segment layout exist
- **AND** backend selection came only from shipped defaults
- **WHEN** startup evaluates migration safety
- **THEN** startup MUST fail naming the directory
- **AND** the error MUST require explicit Chroma keep-and-pin or explicit LanceDB re-ingestion acknowledgement
- **AND** it MUST disclose that automatic migration is not performed

#### Scenario: Explicit LanceDB acknowledges re-ingestion

- **GIVEN** recognised legacy Chroma data exists
- **AND** the operator explicitly selects `VECTOR_STORE=lancedb`
- **WHEN** startup completes
- **THEN** LanceDB MAY start
- **AND** the legacy Chroma directory MUST remain unchanged

#### Scenario: Non-empty unrecognised directory

- **GIVEN** the configured legacy path is non-empty but lacks recognised Chroma markers
- **AND** the backend was not explicitly selected
- **WHEN** startup evaluates migration safety
- **THEN** startup MUST emit an actionable warning rather than classify it as confirmed Chroma data

#### Scenario: Fresh LanceDB installation

- **GIVEN** no recognised legacy Chroma data exists
- **WHEN** default LanceDB setup completes
- **THEN** no migration diagnostic MUST be emitted
