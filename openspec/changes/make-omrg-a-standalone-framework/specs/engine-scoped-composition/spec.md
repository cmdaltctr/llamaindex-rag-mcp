## ADDED Requirements

### Requirement: An engine owns its own composition

The system SHALL provide an engine object that resolves its providers, vector
store and effective settings at construction, and holds them for its own
lifetime. Constructing an engine SHALL NOT mutate process-global state.

#### Scenario: Construction from explicit settings

- **WHEN** an engine is constructed from a settings object supplied by the
  caller
- **THEN** it SHALL use exactly those settings
- **AND** it SHALL NOT read the environment or any configuration file

#### Scenario: Construction from the environment

- **WHEN** an engine is constructed without explicit settings
- **THEN** it SHALL resolve settings through the established precedence rules
- **AND** the result SHALL be equivalent to the settings the server startup
  path would produce

#### Scenario: No process-global mutation

- **WHEN** an engine is constructed
- **THEN** no process-wide default store, default settings object, or
  library-global model assignment SHALL be written as a side effect

#### Scenario: Construction failures are actionable

- **WHEN** a provider, store or model cannot be constructed
- **THEN** construction SHALL fail with an error naming the offending setting
- **AND** the engine SHALL NOT be left partially initialised

### Requirement: Engines are isolated from one another

Two engines constructed in one process with different configurations SHALL
operate independently. Neither SHALL observe the other's providers, store
handles, caches or settings.

#### Scenario: Two engines, two configurations

- **GIVEN** engine A configured for one vector store and engine B for another
- **WHEN** both are used in one process
- **THEN** each SHALL read and write only its own store
- **AND** neither SHALL be affected by the other's construction order

#### Scenario: Derivative caches are engine-scoped

- **GIVEN** two engines over collections sharing a name
- **WHEN** a sparse index or query-embedding cache is populated for one
- **THEN** the other SHALL NOT serve entries from it

#### Scenario: Disposal releases resources

- **WHEN** an engine is disposed
- **THEN** the store handles and model sessions it owns SHALL be released
- **AND** other engines SHALL be unaffected

### Requirement: Embedding-provider selection is engine scoped

An engine SHALL use its own embedding provider and model. Two engines in one
process SHALL be able to use different providers or models simultaneously.

This retires the process-scoped limit recorded in ADR-047 decision 7, which
existed because the underlying library exposes one process-global embedding
model. The engine SHALL NOT depend on that global for its own operations.

#### Scenario: Two engines, two embedding models

- **GIVEN** engine A configured with one embedding model and engine B with
  another
- **WHEN** each ingests into its own collection in one process
- **THEN** each collection's vectors SHALL be produced by that engine's model
- **AND** neither engine's embeddings SHALL be produced by the other's model

#### Scenario: Interleaved operations stay correct

- **GIVEN** two engines with different embedding models
- **WHEN** their ingest and search operations interleave in one process
- **THEN** each operation SHALL use its own engine's model
- **AND** no operation SHALL observe a model swapped in by the other

#### Scenario: Embedding identity still guards the collection

- **WHEN** an engine queries a collection stamped with a different embedding
  identity
- **THEN** the existing embedding-identity guard SHALL reject the operation
- **AND** the rejection SHALL name the mismatch

#### Scenario: Per-collection provider selection is unblocked

- **WHEN** a collection profile declares an embedding provider
- **THEN** the resolved engine for that collection MAY honour it
- **AND** the documented "unsupported" boundary for concurrent per-collection
  providers SHALL no longer apply

### Requirement: The server startup path is one caller of the engine

`ensure_runtime_setup()` SHALL remain available as the server startup path and
SHALL be implemented in terms of the engine: it constructs the default engine
from the environment and installs it as the process default for the existing
transports.

#### Scenario: Existing transports are unchanged

- **WHEN** the MCP server, CLI or watcher starts
- **THEN** it SHALL obtain a working engine
- **AND** its externally observable behaviour SHALL be unchanged by this
  change

#### Scenario: The process default is a convenience, not a requirement

- **WHEN** a caller constructs and uses an engine directly
- **THEN** it SHALL work without the process default having been installed

#### Scenario: Startup remains fail-fast

- **WHEN** startup encounters an invalid provider, store or strategy name
- **THEN** it SHALL fail with the existing actionable error
- **AND** SHALL NOT start with a partially composed runtime
