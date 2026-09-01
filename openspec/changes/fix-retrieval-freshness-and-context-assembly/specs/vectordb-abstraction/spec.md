## ADDED Requirements

### Requirement: Stores expose a durable collection data version

Every registered vector store SHALL expose the data-version capability for a
collection, returning either an opaque durable token or explicit
unavailability. A returned token SHALL change when the collection's rows or
dataset identity change, including overwrite-based schema evolution and
recreation, and SHALL be observable by any process reading the same underlying
data. A numeric version whose history can restart is not sufficient alone.

For LanceDB, the token SHALL combine an OMRG-owned random dataset epoch stored
in current table schema metadata with `table.version`. Ordinary row mutations
SHALL preserve the epoch. Table creation, recreation and every overwrite-based
rebuild SHALL replace it. Version-history timestamps and row counts SHALL NOT
be used as substitutes.

This is distinct from the existing process-local generation counter, which
remains the mechanism for same-process invalidation. A store whose backend
offers no durable version SHALL say so explicitly rather than returning the
process-local counter under a durable name.

#### Scenario: Version advances after a write

- **GIVEN** a collection at durable version v
- **WHEN** rows are written, upserted, or deleted
- **THEN** the durable version SHALL differ from v

#### Scenario: Version is visible across processes

- **GIVEN** process A and process B each hold their own store instance over
  one underlying database
- **AND** both observe durable version v for a collection
- **WHEN** A performs a successful mutation
- **THEN** B SHALL observe a different durable version without any
  inter-process signalling
- **AND** B's process-local generation counter MAY remain unchanged

#### Scenario: Overwrite and recreation cannot collide

- **GIVEN** a cached Lance token containing epoch E and numeric version v
- **WHEN** schema evolution rebuilds the table with overwrite, or the table is
  deleted and recreated, and its numeric version later equals v
- **THEN** the rebuilt table MUST carry a new epoch distinct from E
- **AND** the complete durable token MUST differ from the cached token

#### Scenario: Cleanup does not erase identity

- **GIVEN** a Lance table carrying an OMRG dataset epoch
- **WHEN** old versions are pruned through cleanup or optimisation
- **THEN** the current table MUST retain the same epoch
- **AND** the next ordinary mutation MUST still change the complete token

#### Scenario: Existing table acquires identity on its next write

- **GIVEN** a pre-existing Lance table without an OMRG dataset epoch
- **WHEN** it is read without mutation
- **THEN** the durable-version capability MUST report unavailable and MUST NOT
  mutate the table
- **WHEN** an OMRG-controlled writer next mutates it under the write lock
- **THEN** the writer MUST install an epoch before the row mutation
- **AND** readers MUST treat the change from local fallback to durable token as
  cache invalidation

#### Scenario: Version is stable without mutation

- **GIVEN** a collection with no mutation between two reads
- **WHEN** the durable version is read twice
- **THEN** both reads SHALL return the same value

#### Scenario: Absent collection

- **WHEN** the durable version of a collection that does not exist is
  requested
- **THEN** the store SHALL report absence rather than raising

#### Scenario: Long-lived readers observe recreation

- **GIVEN** process A holds an open Lance store and has observed token T
- **WHEN** process B rebuilds or recreates that collection with a new epoch
- **THEN** A's next data-version read MUST observe a token different from T
- **AND** A MUST NOT require a process restart

#### Scenario: Unsupported backends are explicit

- **GIVEN** a store whose backend exposes no durable version
- **WHEN** the durable version is requested
- **THEN** the store SHALL report the capability as unavailable
- **AND** callers SHALL fall back to the process-local counter with the
  reduced guarantee stated in their own contract


### Requirement: Stores provide bounded filtered row reads

The vector-store abstraction SHALL provide a store-neutral operation that
returns rows matching metadata equality filters without scanning the whole
collection. Both registered adapters SHALL implement the same result and
absence semantics.

#### Scenario: Source-scoped rows are returned

- **GIVEN** rows for multiple sources in one collection
- **WHEN** rows are requested with `source_id = S`
- **THEN** only rows for S SHALL be returned
- **AND** their persisted lineage metadata SHALL be preserved

#### Scenario: Filtered reads are bounded

- **WHEN** a filtered read selects one source from a many-source collection
- **THEN** the adapter SHALL push the filter into the backend
- **AND** SHALL NOT materialise every collection row in Python

#### Scenario: Adapters agree

- **WHEN** the differential store-contract tests exercise a supported equality
  filter, an absent collection and no matches
- **THEN** LanceDB and Chroma SHALL expose equivalent public behaviour
