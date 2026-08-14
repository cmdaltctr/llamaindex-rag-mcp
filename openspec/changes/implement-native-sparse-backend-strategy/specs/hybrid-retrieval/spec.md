## ADDED Requirements

### Requirement: Concrete sparse backends resolve through one contract
The `bm25` and `native` sparse backend names SHALL resolve through one sparse-query contract. The `auto` value SHALL remain a capability-selection policy and SHALL resolve to a concrete registered backend before query execution.

#### Scenario: BM25 is selected
- **WHEN** the effective sparse backend is `bm25`
- **THEN** hybrid retrieval SHALL execute the registered BM25 implementation

#### Scenario: Native is selected and supported
- **WHEN** the effective sparse backend is `native`
- **AND** the installed vector store supports native sparse queries
- **THEN** hybrid retrieval SHALL execute a real registered native sparse implementation
- **AND** SHALL NOT report an empty placeholder ranking as successful

#### Scenario: Auto resolves to native when supported
- **WHEN** the effective sparse backend is `auto`
- **AND** the installed vector store supports native sparse queries
- **THEN** resolution SHALL select the registered `native` backend before query execution

#### Scenario: Auto resolves to BM25 when native is unsupported
- **WHEN** the effective sparse backend is `auto`
- **AND** the installed vector store does not support native sparse queries
- **THEN** resolution SHALL select the registered `bm25` backend without emitting the explicit-native fallback warning

#### Scenario: Unknown concrete backend is configured
- **WHEN** sparse backend resolution produces an unregistered concrete name
- **THEN** startup SHALL fail and list the registered sparse backend names

### Requirement: Native fallback remains explicit
The system SHALL retain BM25 fallback when native sparse capability is absent or fails safely, and SHALL emit a visible warning before returning results.

#### Scenario: Explicit native is unsupported
- **WHEN** `native` is selected but the installed vector store cannot issue native sparse queries
- **THEN** the system SHALL warn and execute BM25
- **AND** SHALL NOT identify the resulting sparse ranking as native

#### Scenario: Native fails safely at query time
- **WHEN** the selected native backend raises a supported runtime error during a sparse query
- **THEN** the hybrid pipeline SHALL fall back to BM25 for that query
- **AND** SHALL emit the visible fallback warning before returning results
- **AND** SHALL NOT label the resulting sparse ranking as native

#### Scenario: Existing collection has mixed sparse coverage
- **WHEN** native retrieval runs against a collection with partial sparse-vector coverage
- **THEN** dense retrieval SHALL still cover every chunk
- **AND** the existing one-shot remediation warning SHALL remain in effect
