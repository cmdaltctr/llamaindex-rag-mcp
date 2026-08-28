## MODIFIED Requirements

### Requirement: Store selection via configuration

The system SHALL select the vector-store implementation through the
`VECTOR_STORE` setting, defaulting to `lancedb` after the registered LanceDB
qualification gate passes. Settings SHALL be resolved in `config/` and object
construction SHALL occur only in `compose.py` through the registry. Selection
SHALL be a registry lookup, not a branch over store names. The constructed
store SHALL be passed to every consumer by injection, including the codebase
map subsystem.

#### Scenario: Default store is resolved from configuration

- **GIVEN** the LanceDB qualification gate passed
- **AND** `VECTOR_STORE` is not explicitly set
- **AND** no recognised legacy Chroma data requires acknowledgement
- **WHEN** runtime composition occurs
- **THEN** `compose.py` MUST construct embedded LanceDB through the registry

#### Scenario: Unknown store value

- **WHEN** `VECTOR_STORE` names an unregistered implementation
- **THEN** startup MUST fail with a clear error listing registered names

#### Scenario: Store is injected into every consumer

- **WHEN** an operation or subsystem needs vector-store access
- **THEN** it MUST receive the store as a parameter or constructor argument
- **AND** it MUST NOT construct one itself

#### Scenario: Alternate store is selectable by configuration

- **GIVEN** the complete `chroma` optional extra is installed
- **AND** `VECTOR_STORE=chroma` is explicitly set
- **WHEN** runtime composition occurs
- **THEN** `compose.py` MUST resolve Chroma through the registry
- **AND** every consumer MUST receive it through the same injection paths

#### Scenario: Access before composition

- **GIVEN** no vector store has been composed or injected
- **WHEN** a core consumer requests process-wide store access
- **THEN** the accessor MUST fail clearly rather than construct a default
