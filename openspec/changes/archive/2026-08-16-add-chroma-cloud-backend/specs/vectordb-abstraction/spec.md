## ADDED Requirements

### Requirement: Chroma implementation SHALL accept an injected client

The Chroma vector-store implementation SHALL support an injected client that
conforms to the Chroma client API. The same implementation SHALL serve local
and cloud deployments; pipeline consumers SHALL remain unaware of the client
type.

#### Scenario: Cloud client injection

- **WHEN** the composition root selects cloud mode
- **THEN** the Chroma store SHALL receive the constructed cloud client
- **AND** all collection operations SHALL use that client

#### Scenario: Local client compatibility

- **WHEN** local mode is selected
- **THEN** the existing persistent-client behaviour and tests SHALL remain unchanged

### Requirement: Chroma client construction SHALL keep one import boundary

All Chroma SDK imports and local/cloud client construction SHALL remain in
`core/vectordb/chroma.py`. The composition root SHALL pass resolved primitive
settings into the Chroma factory without importing or constructing a Chroma
SDK client itself.

#### Scenario: Single chromadb import site after cloud support

- **WHEN** production source is searched for direct `chromadb` imports
- **THEN** `core/vectordb/chroma.py` SHALL remain the only matching module
