## Purpose

Defines a consistent vector-store policy for future experiments so evidence uses the supported LanceDB base path unless the experiment deliberately compares or evaluates another backend.

## ADDED Requirements

### Requirement: Future experiments SHALL use LanceDB by default

Every new experiment that requires a vector store SHALL select LanceDB unless vector-store backend is a declared manipulated factor. The plan and runtime manifest SHALL record the requested and effective backend.

#### Scenario: Store is not a manipulated factor

- **WHEN** a new experiment indexes or queries vectors without comparing stores
- **THEN** its plan MUST select LanceDB
- **AND** every cited cell MUST prove LanceDB as the effective backend

#### Scenario: Experiment compares vector stores

- **WHEN** vector-store backend is a declared manipulated factor
- **THEN** non-LanceDB cells MAY run through their required optional extras
- **AND** the plan MUST name the store factor and the reason for every backend

### Requirement: Historical experiment evidence SHALL remain immutable

Changing the default SHALL NOT rewrite completed ChromaDB experiment records or claim they ran on LanceDB.

#### Scenario: Reading historical evidence

- **WHEN** a completed experiment records ChromaDB in its manifest
- **THEN** its raw artefacts and verdict MUST remain unchanged
- **AND** new summaries MUST describe the recorded backend accurately
