## ADDED Requirements

### Requirement: An engine owns its own composition

The system SHALL provide an engine object owning its vector store, embedder,
reranker, profile resolver and effective settings for its own lifetime.
Concrete provider, store, reranker and capability construction SHALL remain
in the composition root: a composition-root builder SHALL construct the
dependencies and return an Engine owning them. The engine SHALL NOT itself
instantiate concrete providers or stores, so the composition root remains
the sole construction root.

Because `EffectiveSettings` deliberately excludes construction-time values
(including Chroma Cloud credentials), the engine constructor SHALL accept
already-composed dependencies rather than resolving them from settings. An
environment factory (`compose.build_engine()`) SHALL resolve settings,
construct the dependencies and return an Engine; `Engine.from_environment()`
SHALL delegate to it. Optional answer completion SHALL be resolved lazily
when `answer()` is used.

Constructing an engine — directly or from the environment — SHALL NOT mutate
process-global state.

#### Scenario: Construction from explicit settings

- **WHEN** an engine is constructed from caller-supplied dependencies and
  settings
- **THEN** it SHALL use exactly those settings and dependencies
- **AND** it SHALL NOT read the environment or any configuration file
- **AND** it SHALL NOT construct concrete providers or stores itself

#### Scenario: Construction from the environment

- **WHEN** `Engine.from_environment()` is called
- **THEN** it SHALL delegate to the composition-root environment factory
- **AND** the composition root SHALL remain the sole production caller of
  `get_settings()` outside its sanctioned sibling modules
- **AND** no process-global state SHALL be installed as a side effect

#### Scenario: No process-global mutation

- **WHEN** an engine is constructed, directly or from the environment
- **THEN** no process-wide default store, default settings object, or
  library-global model assignment SHALL be written as a side effect

#### Scenario: Construction failures are actionable

- **WHEN** a required provider, store or model cannot be constructed
- **THEN** construction SHALL fail with an error naming the offending setting
- **AND** the engine SHALL NOT be left partially initialised

### Requirement: Engines are isolated from one another

Two engines constructed in one process with different configurations SHALL
operate independently. Neither SHALL observe the other's mutable providers,
store handles, derivative caches or settings. Operations on a directly
constructed engine SHALL NOT read process-default stores or settings:
ingestion SHALL use the engine's injected store, and store operational
fallbacks (scan page size, connection URI, persist directory) SHALL resolve
from construction-time state rather than process defaults. Immutable model
artefacts MAY be shared through the existing keyed process cache when
lifetime ownership is reference-safe.

#### Scenario: Two engines, two configurations

- **GIVEN** engine A configured for one vector store and engine B for another
- **WHEN** both are used in one process
- **THEN** each SHALL read and write only its own store
- **AND** neither SHALL be affected by the other's construction order

#### Scenario: Direct-engine paths bypass process defaults

- **GIVEN** an engine constructed directly, with no process-default store or
  process-default effective settings installed
- **WHEN** it ingests, searches densely, runs hybrid/BM25 retrieval, and
  lists or pages collections
- **THEN** every path SHALL succeed using only engine-owned dependencies
- **AND** no path SHALL call `get_default_store()` or
  `get_default_effective_settings()`

#### Scenario: Derivative caches are engine-scoped

- **GIVEN** two engines over collections sharing a name
- **WHEN** a sparse index or query-embedding cache is populated for one
- **THEN** the other SHALL NOT serve entries from it

#### Scenario: Disposal releases resources

- **WHEN** an engine is disposed
- **THEN** its owned store handle SHALL be released through the store's
  lifecycle method and its derivative caches SHALL be released
- **AND** sparse-cache eviction SHALL be limited to that engine's stores'
  identity namespace, leaving other engines' entries intact
- **AND** shared model artefacts SHALL remain available while another engine
  references them
- **AND** process-wide ingestion coordination primitives (write lock, embed
  semaphores, shutdown event) SHALL NOT be touched
- **AND** other engines SHALL remain functional

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

#### Scenario: Different engines may target different providers

- **GIVEN** two collections requiring different embedding providers
- **WHEN** the caller constructs one explicitly configured Engine for each
- **THEN** both SHALL operate concurrently in one process
- **AND** profile-driven provider routing inside one Engine SHALL remain out
  of scope

### Requirement: The server startup path is one caller of the engine

`ensure_runtime_setup()` SHALL remain available as the server startup path
and SHALL be implemented as an installer over the composition-root builder:
it builds the default engine from the environment and installs it as the
process default for the existing transports, assigning the library-global
embedding model only for legacy transport compatibility. The builder itself
SHALL NOT install anything.

#### Scenario: Existing transports are unchanged

- **WHEN** the MCP server, CLI or watcher starts
- **THEN** it SHALL obtain a working engine
- **AND** its externally observable behaviour SHALL be unchanged by this
  change

#### Scenario: Optional answering is lazy

- **GIVEN** an Engine whose retrieval dependencies are available but whose
  answer provider or optional extra is absent
- **WHEN** the Engine is constructed and `search()` is used
- **THEN** construction and search MUST succeed
- **AND** the actionable failure MUST occur only if `answer()` is used

#### Scenario: The process default is a convenience, not a requirement

- **WHEN** a caller constructs and uses an engine directly
- **THEN** it SHALL work without the process default having been installed
- **AND** a full ingest/search path SHALL remain correct when the LlamaIndex
  global embedder is a throwing sentinel

#### Scenario: Startup remains fail-fast

- **WHEN** startup encounters an invalid provider, store or strategy name
- **THEN** it SHALL fail with the existing actionable error
- **AND** SHALL NOT start with a partially composed runtime
