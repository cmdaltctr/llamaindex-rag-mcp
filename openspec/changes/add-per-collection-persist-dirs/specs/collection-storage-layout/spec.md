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
at `{lancedb_uri}/{collection_name}.lance`. This requirement pins the
on-disk layout only. It makes no claim about write concurrency: within
one process, mutations serialise on the process-global ingestion mutation
lock regardless of collection, and concurrent writes from separate
processes are unverified.

#### Scenario: Two LanceDB collections resolve to distinct storage

- **WHEN** two collections are created in one LanceDB store
- **THEN** each MUST occupy a distinct `.lance` directory under the URI

#### Scenario: Layout regression is pinned against a real store

- **WHEN** the regression test creates two collections in a real
  temporary LanceDB store
- **THEN** the observed table paths MUST remain
  `{lancedb_uri}/{collection_name}.lance` for each collection
- **AND** a future adapter change that co-locates collections MUST fail
  the test

### Requirement: Storage layout documentation states concurrency honestly

The documented storage-layout contract SHALL distinguish the
process-level ingestion mutation lock (process-global, serialises
mutations across collections within one process), the backend's physical
table/directory layout, and cross-process write safety. The documentation
SHALL state that concurrent writes from separate processes are unverified
for both backends.

#### Scenario: Documentation separates the three layers

- **WHEN** a reader consults the storage-layout documentation
- **THEN** it MUST find the process-global mutation lock, the per-backend
  on-disk layout, and cross-process write safety described as distinct
  concerns
- **AND** it MUST NOT find any claim that cross-collection writes are
  contention-free
