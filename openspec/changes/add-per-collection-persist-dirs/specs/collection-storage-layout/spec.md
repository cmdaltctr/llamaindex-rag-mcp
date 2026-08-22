## ADDED Requirements

### Requirement: Collection names are safe path components

Collection and group names SHALL be validated before any filesystem path
is constructed. Each name MUST be a non-empty, single path component.
Absolute paths, separators, `.` and `..` MUST be rejected on every
backend.

#### Scenario: Unsafe collection or group name is rejected

- **WHEN** a collection or group name is empty, absolute, contains `/` or
  `\\`, or equals `.` or `..`
- **THEN** path resolution MUST fail with a clear error
- **AND** no filesystem path MUST be created

### Requirement: LanceDB collections are isolated by native layout

The system SHALL store each LanceDB collection as its own table directory
at `{lancedb_uri}/{collection_name}.lance`. Operations on different
collections SHALL NOT share a table directory or a per-collection write
lock.

#### Scenario: Two LanceDB collections resolve to distinct storage

- **WHEN** two collections are created in one LanceDB store
- **THEN** each MUST occupy a distinct `.lance` directory under the URI
- **AND** concurrent writes to the two collections MUST NOT serialise on
  a shared collection-level file lock

### Requirement: Chroma local collections are isolated by default

When the Chroma backend runs in local mode, the system SHALL resolve each
unmapped collection to `{chroma_persist_dir}/{collection_name}/`, giving
each collection its own SQLite file. Operations for different resolved
directories SHALL use different store instances.

#### Scenario: Two unmapped Chroma collections are isolated

- **WHEN** operations select stores for two different unmapped collections
- **THEN** their resolved persist directories MUST differ
- **AND** their selected store instances MUST differ

### Requirement: Explicit mappings opt into shared Chroma storage

The system SHALL resolve a mapped collection to
`{chroma_persist_dir}/{group_name}/`. Collections mapped to the same group
SHALL reuse one store instance and one SQLite database.

#### Scenario: Two Chroma collections share an explicit group

- **WHEN** two collection names map to the same group name
- **THEN** their resolved persist directories MUST be equal
- **AND** their selected store instance MUST be shared

### Requirement: Flat-layout Chroma migration preserves stored records

The system SHALL migrate each collection from a legacy flat
`chroma_persist_dir` through the ChromaDB API. It SHALL copy IDs,
embeddings, documents and metadata without invoking the embedding
provider. The migration SHALL operate only when the Chroma backend is
selected and SHALL NOT touch LanceDB stores.

#### Scenario: Migration preserves Chroma collection data

- **WHEN** a flat-layout Chroma collection is migrated to its resolved
  directory
- **THEN** its IDs, embeddings, documents and metadata MUST match the
  source
