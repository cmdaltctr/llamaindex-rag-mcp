## Purpose

Defines the effective vector-store policy for every experiment that has not yet
produced its first admissible measured row when ADR-049 takes effect.

## ADDED Requirements

### Requirement: Not-yet-measured experiments SHALL use LanceDB by default

Every experiment whose first admissible measured run occurs after ADR-049 and
that requires a vector store SHALL select LanceDB unless backend is a declared
manipulated factor. Directory creation date SHALL NOT exempt a prepared
experiment. Plan, preflight and runtime manifest SHALL record requested and
effective backend and immutable index identity.

#### Scenario: Prepared Stage 6 experiment has not run

- **GIVEN** an experiment plan or runner existed before ADR-049
- **AND** it has no admissible measured rows
- **WHEN** its execution is prepared after ADR-049
- **THEN** it MUST use and prove LanceDB
- **OR** declare vector store as a manipulated factor with an explicit limitation

#### Scenario: Store is not a manipulated factor

- **WHEN** an experiment indexes or queries vectors without comparing stores
- **THEN** its plan MUST select LanceDB
- **AND** every cited cell MUST prove LanceDB and the expected index identity

#### Scenario: Experiment compares vector stores

- **WHEN** vector-store backend is a declared manipulated factor
- **THEN** non-LanceDB cells MAY use their required optional extras
- **AND** the plan MUST name the factor, reason and backend-specific limitations

### Requirement: Pending Stage 6 harnesses SHALL be inventoried before calibration

Existing prepared calibration plans and runners SHALL be reviewed before their
first measured run. Their immutable indexes SHALL be rebuilt/ported to LanceDB
or their Chroma dependency SHALL be declared as a controlled factor.

#### Scenario: Stage 6 preflight

- **WHEN** a pending calibration experiment reaches preflight
- **THEN** its plan and runner MUST agree on the selected backend
- **AND** preflight MUST assert `vector_store.backend == lancedb` unless the plan declares the store factor
- **AND** an ambient default MUST NOT be accepted as proof

### Requirement: Historical experiment evidence SHALL remain immutable

Changing the default SHALL NOT rewrite completed experiment raw artefacts,
manifests, protocols or verdicts.

#### Scenario: Completed Chroma evidence is referenced

- **WHEN** a completed experiment records ChromaDB
- **THEN** its evidence MUST remain unchanged
- **AND** new summaries MUST describe its recorded backend accurately
- **AND** any later qualification or security information MUST be an append-only dated addendum
