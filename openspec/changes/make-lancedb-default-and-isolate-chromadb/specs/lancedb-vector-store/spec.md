## ADDED Requirements

### Requirement: LanceDB SHALL be the base-install vector-store default

The system SHALL resolve LanceDB when `VECTOR_STORE` is unset. The default path SHALL use an embedded local LanceDB directory and SHALL NOT import or require ChromaDB.

#### Scenario: Unset vector-store selector

- **GIVEN** a base installation without optional extras
- **AND** `VECTOR_STORE` is unset
- **WHEN** runtime setup constructs the vector store
- **THEN** it MUST construct embedded LanceDB
- **AND** `chromadb` MUST remain absent from loaded modules

#### Scenario: Explicit LanceDB selection

- **GIVEN** `VECTOR_STORE=lancedb`
- **WHEN** runtime setup completes
- **THEN** the store MUST connect to the configured `LANCEDB_URI`
- **AND** all ingestion, retrieval, profile, and deletion operations MUST use that store

### Requirement: Existing Chroma data SHALL receive migration guidance

The default change SHALL NOT present an existing Chroma directory as LanceDB data. When the store selector is unset and a non-empty legacy Chroma directory is detected, startup SHALL warn that the data requires explicit Chroma selection or re-ingestion.

#### Scenario: Legacy Chroma directory found after upgrade

- **GIVEN** `VECTOR_STORE` was not explicitly set
- **AND** the configured Chroma directory contains data
- **WHEN** LanceDB becomes the resolved default
- **THEN** startup MUST emit one warning naming the legacy directory
- **AND** the warning MUST explain how to install the `chroma` extra and select Chroma
- **AND** it MUST offer re-ingestion into LanceDB as the supported migration path

#### Scenario: Fresh LanceDB installation

- **GIVEN** `VECTOR_STORE` is unset
- **AND** no non-empty legacy Chroma directory exists
- **WHEN** runtime setup completes
- **THEN** no migration warning MUST be emitted
