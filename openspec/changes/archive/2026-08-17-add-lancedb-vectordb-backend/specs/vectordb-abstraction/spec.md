# Spec: vectordb-abstraction

## MODIFIED Requirements

### Requirement: Store selection via configuration

The system SHALL select the vector store implementation via a
`VECTOR_STORE` environment variable defaulting to `chroma`, read from
`config/` and resolved in `compose.py` through the vector-store registry
(`core/vectordb/registry.py`). Selection SHALL be a registry lookup, not a
branch over the store name (architecture invariant #10). The constructed
store SHALL be passed to consumers by injection, including to the codebase
map subsystem under `core/codebase/`.

#### Scenario: Default is chroma

- **WHEN** `VECTOR_STORE` is not set
- **THEN** `compose.py` MUST construct the ChromaDB implementation

#### Scenario: Unknown store value

- **WHEN** `VECTOR_STORE` names an implementation with no registered
  implementation
- **THEN** the system MUST fail at startup with a clear error listing
  available implementations

#### Scenario: Store is injected into every consumer

- **WHEN** an operation or subsystem needs vector store access
- **THEN** it MUST receive the store as a parameter or constructor argument
- **AND** it MUST NOT construct one itself

#### Scenario: LanceDB is selectable by configuration

- **WHEN** `VECTOR_STORE=lancedb` is set
- **THEN** `compose.py` MUST resolve and construct the LanceDB
  implementation through the registry
- **AND** every consumer MUST receive it by injection through the same
  paths that receive the ChromaDB store
