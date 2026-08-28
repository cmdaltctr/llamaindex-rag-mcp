# Spec: vector-store-registry

## ADDED Requirements

### Requirement: Vector stores SHALL be selected through a registry

The system SHALL select the vector store implementation through a registry
in `core/vectordb/registry.py`, following the pattern of
`core/retrieval/registry.py`. Concrete stores SHALL register lazily under
their configured `VECTOR_STORE` name. `compose.py` SHALL resolve the store
by looking the configured name up in the registry. The dispatch path SHALL
NOT branch `if/elif` over store names and SHALL NOT import a concrete store
module at module level (architecture invariant #10).

#### Scenario: Registered names resolve to their implementation

- **WHEN** `VECTOR_STORE=chroma` or `VECTOR_STORE=lancedb` is set
- **THEN** `compose.py` MUST construct the implementation registered under
  that name
- **AND** it MUST obtain the implementation through the registry lookup, not
  a branch over the name

#### Scenario: No if/elif over store names

- **WHEN** `compose.py` and `core/vectordb/registry.py` are inspected
- **THEN** neither MUST contain an `if/elif` chain over vector-store names
- **AND** the dispatch module MUST NOT import a concrete store module at
  module top level

#### Scenario: Unknown store name fails clearly

- **WHEN** `VECTOR_STORE` names a store with no registered implementation
- **THEN** the system MUST fail at startup with an error listing the
  registered store names

#### Scenario: Adding a store is one file plus one registration

- **WHEN** a new vector store is added
- **THEN** it MUST require one new module implementing the `VectorStore`
  ABC and one `register()` call
- **AND** it MUST NOT require edits to a dispatch branch
