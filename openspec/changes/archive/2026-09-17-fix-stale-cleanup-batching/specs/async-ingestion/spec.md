# Delta: async-ingestion

## MODIFIED Requirements

### Requirement: Replacement preserves the last durable searchable version on failure

Updating an already-indexed source SHALL NOT delete the last durable searchable version merely because a later parse, chunk, embedding or store-write step fails. New-version rows SHALL become durable and be verified before stale-version rows are removed, or another store-neutral mechanism SHALL provide the same safety property. Removal of stale rows SHALL succeed for a source of any row count; where a store caps the number of IDs one delete call accepts, the removal SHALL issue multiple delete calls, each within that cap.

#### Scenario: Parse failure during update
- **GIVEN** version A of a source is indexed and searchable
- **AND** a replacement ingest fails during parsing
- **WHEN** the operation returns an error for that source
- **THEN** version A MUST remain searchable

#### Scenario: Embedding failure during update
- **GIVEN** version A is indexed
- **AND** replacement version B parses/chunks but embedding fails
- **THEN** version A MUST remain searchable

#### Scenario: Store-write failure during update
- **GIVEN** version A is indexed
- **AND** writing version B fails before durability is verified
- **THEN** version A MUST remain searchable

#### Scenario: Successful replacement
- **GIVEN** version A is indexed
- **WHEN** version B is written and verified successfully
- **THEN** stale version A rows SHALL be removed
- **AND** public retrieval SHALL resolve the source to version B without persistent duplicates

#### Scenario: Successful replacement with more rows than one delete call accepts
- **GIVEN** version A is indexed with more than 100 chunk rows
- **WHEN** version B is written and verified successfully
- **THEN** every stale version A row SHALL be removed across multiple delete calls of at most 100 IDs each
- **AND** the operation SHALL report success for that source
- **AND** only version B text SHALL remain searchable for that source
