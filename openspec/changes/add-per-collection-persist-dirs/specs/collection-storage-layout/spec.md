## ADDED Requirements

### Requirement: Collections use isolated storage by default

The system SHALL resolve each unmapped collection to
`{chroma_persist_dir}/{collection_name}/` before constructing its vector
store. Operations for different resolved directories SHALL use different
store instances.

#### Scenario: Two unmapped collections are isolated

- **WHEN** operations select stores for two different unmapped collections
- **THEN** their resolved persist directories MUST differ
- **AND** their selected store instances MUST differ

### Requirement: Explicit mappings opt into shared storage

The system SHALL resolve a mapped collection to
`{chroma_persist_dir}/{group_name}/`. Collections mapped to the same group
SHALL reuse one store instance and one SQLite database.

#### Scenario: Two collections share an explicit group

- **WHEN** two collection names map to the same group name
- **THEN** their resolved persist directories MUST be equal
- **AND** their selected store instance MUST be shared

### Requirement: Storage path components are safe

Collection and group names SHALL be validated before path construction. Each
name MUST be a non-empty, single path component. Absolute paths, separators,
`.` and `..` MUST be rejected.

#### Scenario: Unsafe collection or group name is rejected

- **WHEN** a collection or group name is empty, absolute, contains `/` or
  `\\`, or equals `.` or `..`
- **THEN** persist-directory resolution MUST fail with a clear error
- **AND** no filesystem path MUST be created

### Requirement: Flat-layout migration preserves stored records

The system SHALL migrate each collection from the configured flat
`chroma_persist_dir` through the ChromaDB API. It SHALL copy IDs, embeddings,
documents and metadata without invoking the embedding provider.

#### Scenario: Migration preserves collection data

- **WHEN** a flat-layout collection is migrated to its resolved directory
- **THEN** its IDs, embeddings, documents and metadata MUST match the source
- **AND** the embedding provider MUST NOT be called

#### Scenario: Configured source root is honoured

- **WHEN** `chroma_persist_dir` or `--root` selects a non-default source root
- **THEN** migration MUST read that root instead of hard-coded `./chroma_db`

### Requirement: Migration is resumable and reversible

The migration SHALL back up the source and existing destinations before
writes. It SHALL stage and verify imports before swapping destinations. Exact
prior imports SHALL be skipped, while conflicting data SHALL stop migration
without overwriting either copy.

#### Scenario: Exact migration re-run is idempotent

- **WHEN** migration runs again after an exact prior import
- **THEN** matching IDs, embeddings, documents and metadata MUST be skipped
- **AND** no duplicate records MUST be created

#### Scenario: Partial failure can resume or roll back

- **WHEN** an import fails after at least one collection completes
- **THEN** source data and retained destination backups MUST remain intact
- **AND** a re-run MUST complete remaining collections without duplication
- **AND** rollback MUST restore the pre-migration layout

### Requirement: Mapping changes require explicit data movement

The system SHALL NOT move data when `collection_group_map` changes. After a
collection's first write, own-to-group, group-to-own and group-to-group changes
SHALL require migration or re-ingestion before the new mapping is used.

#### Scenario: Existing collection mapping changes

- **WHEN** an existing collection resolves to a different directory
- **THEN** the system MUST NOT move existing data automatically
- **AND** the operator MUST run the documented storage migration or re-ingest
  the collection

### Requirement: Separate directories isolate process writes

The system SHALL allow different operating-system processes to write
concurrently to different unmapped collections under one parent root without
sharing a ChromaDB SQLite file.

#### Scenario: Concurrent writes use separate databases

- **WHEN** two operating-system processes start overlapping writes to two
  unmapped collections under one `chroma_persist_dir`
- **THEN** neither write MUST fail with a database-lock error
- **AND** both collections MUST contain their expected records
