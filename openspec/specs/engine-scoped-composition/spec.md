# engine-scoped-composition Specification

## Purpose
Defines how an engine object owns its composition — vector store, embedder,
reranker and profile resolver — for its own lifetime, so that two engines in
one process operate in isolation without relying on process-global state.

## Requirements

### Requirement: An engine owns its own composition

The system SHALL provide an engine object constructed from explicit
`EffectiveSettings`, owning its vector store, embedder, reranker, profile
resolver, and injected graph-operation catalogue for its own lifetime.
Environment resolution SHALL use a factory that delegates to the composition
root. Optional answer completion SHALL be resolved lazily when answering is
used, including through a graph. Constructing an engine SHALL NOT mutate
process-global state. Runs SHALL borrow composed resources rather than
constructing or closing their own providers.

#### Scenario: Construction from explicit settings

- **WHEN** an engine is constructed from a settings object supplied by the
  caller
- **THEN** it SHALL use exactly those settings
- **AND** it SHALL NOT read the environment or any configuration file

#### Scenario: Construction from the environment

- **WHEN** `Engine.from_environment()` is called
- **THEN** it SHALL delegate to the composition-root environment factory
- **AND** the composition root SHALL remain the sole production caller of
  `get_settings()`

#### Scenario: No process-global mutation

- **WHEN** an engine is constructed
- **THEN** no process-wide default store, default settings object, or
  library-global model assignment SHALL be written as a side effect

#### Scenario: Construction failures are actionable

- **WHEN** a required provider, store or model cannot be constructed
- **THEN** construction SHALL fail with an error naming the offending setting
- **AND** the engine SHALL NOT be left partially initialised

#### Scenario: Graph adapters use injected composition

- **WHEN** a graph operation requires storage, embedding, OCR, or completion
- **THEN** it SHALL receive the Engine's composed resource through an injected
  adapter
- **AND** it SHALL NOT read global defaults or build a provider independently

#### Scenario: Graph adapters are covered by the default-accessor guard

- **WHEN** a graph-adapter module is added
- **THEN** the default-accessor guard SHALL list that module and reject any
  default settings or default store accessor in it
- **AND** a behavioural test with poisoned process defaults SHALL fail when
  an adapter drops `store` or `settings` from its core call

#### Scenario: Answering remains lazy for graphs

- **WHEN** a graph performs retrieval without generation
- **THEN** optional answering and judge providers SHALL remain unconstructed

#### Scenario: Explicit Engine lacks named-profile support

- **WHEN** a graph requests a named profile that an explicitly constructed
  Engine cannot resolve through its supplied dependencies
- **THEN** validation SHALL fail with an actionable capability message
- **AND** it SHALL NOT silently resolve environment or configuration files

### Requirement: Engines are isolated from one another

Two engines constructed in one process with different configurations SHALL
operate independently. Neither SHALL observe the other's mutable providers,
store handles, derivative caches or settings. Immutable model artefacts MAY be
shared through the existing keyed process cache when lifetime ownership is
reference-safe.

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
- **THEN** its owned store handle and derivative caches SHALL be released
- **AND** shared model artefacts SHALL remain available while another engine
  references them
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
- **AND** profile-driven provider routing inside one Engine SHALL remain out of
  scope

### Requirement: The server startup path is one caller of the engine

`ensure_runtime_setup()` SHALL remain available as the startup path for the CLI and the watcher and SHALL be implemented in terms of the engine: it constructs the default engine from the environment and installs it as the process default for those transports. The MCP server SHALL NOT call it; the MCP lifespan constructs or receives its Engine directly.

#### Scenario: Existing transports are unchanged

- **WHEN** the MCP server, CLI or watcher starts
- **THEN** it SHALL obtain a working engine
- **AND** its tools and commands SHALL return the same results as before this change

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

### Requirement: Graph resource leases protect Engine ownership
Active graph runs SHALL lease their Engine's resources. A run SHALL release its leases on success, failure, or safe cancellation. Closing an Engine with active graph leases SHALL fail clearly without releasing those resources. A composed web runtime SHALL drain its owned runs before close.

#### Scenario: One run completes
- **WHEN** a graph completes
- **THEN** its leases SHALL be released
- **AND** the Engine and other runs SHALL remain usable

#### Scenario: Close is requested while a graph is active
- **WHEN** a caller requests close with active graph leases
- **THEN** close SHALL report the active-work condition
- **AND** providers and store handles SHALL remain available until the caller drains the work

#### Scenario: Another Engine is disposed
- **WHEN** another Engine closes
- **THEN** the graph's resources, caches, and immutable shared model artefacts SHALL remain valid under the existing ownership rules

### Requirement: Graph cancellation is run scoped
Graph cancellation SHALL not set or clear a process-global shutdown flag for unrelated work. Provider and write concurrency SHALL retain existing limits. Shared mutable diagnostics and caches SHALL be protected or isolated before concurrent access.

#### Scenario: One run is cancelled
- **WHEN** one graph run is cancelled
- **THEN** another admitted run or explicit Engine operation SHALL not inherit that cancellation

#### Scenario: Shared inference state is unsafe for parallel use
- **WHEN** ready nodes share mutable model diagnostics or an unsafe cache
- **THEN** access SHALL be serialised or isolated
- **AND** one run SHALL not report another run's diagnostic state

### Requirement: The engine answers with a client completion or resolved rows

`Engine.answer` SHALL accept an optional client completion (a completion function, a source label of `client_mrtr` or `client_legacy`, and a round cap) and optional pre-resolved retrieval rows. A client completion SHALL replace only the answer model: claim verification SHALL stay with the engine's own verifier. The result SHALL report the client completion's source label, and synthesis SHALL run no more rounds than its cap. When rows are given, the engine SHALL NOT retrieve again. Without either argument, the result SHALL equal the result before this change.

#### Scenario: Client model, server verifier

- **WHEN** `answer` runs with a client completion and claim verification enabled
- **THEN** the answer MUST come from the client completion, verification MUST use the engine's verifier, and the completion source MUST be the client's label

#### Scenario: Round cap

- **WHEN** the answer block allows 8 rounds and the client completion's cap is 4
- **THEN** synthesis MUST run at most 4 rounds

#### Scenario: Resolved rows

- **WHEN** `answer` runs with rows
- **THEN** the engine MUST NOT run a retrieval

#### Scenario: Default unchanged

- **WHEN** `answer` runs with neither argument
- **THEN** the result MUST equal the result before this change for the same input and models

### Requirement: The engine redacts its configured credentials

Every engine SHALL carry the credential values it was composed with (the Chroma Cloud API key, tenant and database, and the OpenRouter key) and SHALL expose `redact(text)`, which removes each value and every prefix of six or more characters of the keys. Transports SHALL redact error text that leaves the process through the engine they use. Credentials SHALL NOT be added to `EffectiveSettings`.

#### Scenario: Cloud tenant in an MCP error

- **WHEN** an MCP tool fails with an exception whose text holds the Chroma Cloud tenant and database
- **THEN** the returned error dict and the log line MUST NOT contain either value

#### Scenario: Key prefix in a REST job failure

- **WHEN** a web ingest job fails with an exception whose text holds the first eight characters of the OpenRouter key
- **THEN** the job's error body MUST NOT contain them
