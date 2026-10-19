# Engine-scoped composition delta

## MODIFIED Requirements

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

## ADDED Requirements

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
