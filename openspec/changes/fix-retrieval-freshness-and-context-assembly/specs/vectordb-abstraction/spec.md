## ADDED Requirements

### Requirement: Stores expose a durable collection data version

Every registered vector store SHALL expose a durable data version for a
collection: a value that changes when the collection's rows change, and that
is observable by any process reading the same underlying data — not only by
the process that performed the write.

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

#### Scenario: Version is stable without mutation

- **GIVEN** a collection with no mutation between two reads
- **WHEN** the durable version is read twice
- **THEN** both reads SHALL return the same value

#### Scenario: Absent collection

- **WHEN** the durable version of a collection that does not exist is
  requested
- **THEN** the store SHALL report absence rather than raising

#### Scenario: Unsupported backends are explicit

- **GIVEN** a store whose backend exposes no durable version
- **WHEN** the durable version is requested
- **THEN** the store SHALL report the capability as unavailable
- **AND** callers SHALL fall back to the process-local counter with the
  reduced guarantee stated in their own contract
