## ADDED Requirements

### Requirement: Settings SHALL resolve one LanceDB default with source provenance

After the qualification pause gate passes, every executable default surface
SHALL agree on `lancedb`, including the typed settings resolver, YAML defaults
and `EffectiveSettings`. Resolution SHALL retain whether the backend came from
explicit user input or shipped defaults.

#### Scenario: Default resolution

- **GIVEN** no backend is supplied by constructor/CLI, environment or `.env`
- **WHEN** settings are resolved
- **THEN** the effective selector MUST be `lancedb`
- **AND** its provenance MUST be recorded as a shipped default

#### Scenario: Explicit selection is preserved

- **GIVEN** the user explicitly supplies a supported backend
- **WHEN** settings are resolved
- **THEN** the effective selector MUST equal that backend
- **AND** its provenance MUST be explicit

#### Scenario: Default surfaces agree

- **WHEN** the typed settings model, YAML defaults, effective-settings model and environment example are inspected by the drift test
- **THEN** all MUST identify LanceDB as the default

### Requirement: compose.py SHALL remain the sole vector-store constructor

Only `compose.py` SHALL resolve the selected registry entry and instantiate a
vector store. Core accessors and consumers SHALL receive or return injected
instances and SHALL not construct fallback stores.

#### Scenario: Uncomposed process-wide access

- **GIVEN** composition has not installed a process-wide store
- **WHEN** an accessor is called
- **THEN** it MUST fail clearly
- **AND** it MUST NOT import settings, compose or a concrete backend

### Requirement: Chroma compatibility SHALL be validated before credentials

Chroma settings SHALL be cross-validated against the selected backend before
credential completeness. Credential values SHALL never appear in errors.

#### Scenario: Cloud mode and LanceDB with missing API key

- **GIVEN** `VECTOR_STORE=lancedb`
- **AND** `CHROMA_MODE=cloud`
- **AND** no Chroma API key is supplied
- **WHEN** settings are validated
- **THEN** the error MUST state that Chroma settings require `VECTOR_STORE=chroma`
- **AND** it MUST NOT report the missing-key error first

#### Scenario: Partial or whitespace credentials with LanceDB

- **GIVEN** LanceDB is selected
- **AND** any Chroma credential remains non-empty after trimming
- **WHEN** settings are validated
- **THEN** backend mismatch MUST be reported without exposing the value

### Requirement: Configuration documentation SHALL reflect installation and rollback

Current documentation SHALL state LanceDB as the qualified default, Chroma as
an optional explicit backend, recognised-legacy fail-closed behaviour, and the
data-aware rollback procedure.

#### Scenario: Operator documentation is inspected

- **WHEN** active configuration, migration and rollback guidance is read
- **THEN** it MUST provide source-checkout and packaged-extra Chroma installation forms
- **AND** rollback MUST require pinning and verifying LanceDB before reverting software
- **AND** historical ADRs MUST be marked superseded by link rather than rewritten
