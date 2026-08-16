## ADDED Requirements

### Requirement: Storage mode SHALL be resolved at the composition root

Configuration SHALL parse and validate Chroma mode and connection values as
pure data. `compose.build_vector_store(settings)` SHALL pass the resolved
mode and connection values to the registered Chroma factory. The config
package SHALL NOT import ChromaDB or construct a client.

#### Scenario: Local store construction

- **WHEN** resolved settings select local mode
- **THEN** the composition root SHALL pass the configured persist directory
  to the Chroma factory

#### Scenario: Cloud store construction

- **WHEN** resolved settings select cloud mode
- **THEN** the composition root SHALL pass the API key and optional
  tenant/database identifiers to the Chroma factory
- **AND** it SHALL NOT pass the local persist directory as an active storage target

#### Scenario: No credentials in effective operation settings

- **WHEN** the composition root builds `EffectiveSettings` for core operations
- **THEN** cloud API credentials SHALL NOT be copied into that value object
- **AND** credentials SHALL remain confined to construction-time settings

### Requirement: Runtime setup SHALL validate explicit cloud selection

Runtime setup SHALL construct and validate the selected cloud connection
before registering the default vector store. Failure SHALL leave no partially
registered default store.

#### Scenario: Cloud validation fails during startup

- **WHEN** cloud client construction or its connection check raises
- **THEN** runtime setup SHALL return or raise an actionable startup failure
- **AND** the process default store SHALL remain unset
