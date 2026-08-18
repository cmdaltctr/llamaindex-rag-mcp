## MODIFIED Requirements

### Requirement: Directory ingestion has bounded in-memory node lifetime

`ingest_path_async()` SHALL NOT retain every emitted node for an arbitrarily large directory before the first write. The pipeline SHALL process and persist explicitly bounded units, with one source file at a time as the minimum acceptable bound unless a smaller batch is required for a single large file.

#### Scenario: Corpus size increases by file count
- **GIVEN** a generated corpus of many independent files
- **WHEN** the corpus is ingested
- **THEN** the number of simultaneously retained source-file node sets MUST remain bounded independently of total file count
- **AND** successful earlier files MAY become durable before later files have been parsed

### Requirement: Unchanged files skip expensive reprocessing using complete index identity

The ingestion pipeline SHALL persist a source-content identity and an index-shaping identity for each stored source version. A file MAY be skipped as unchanged only when its content identity and every index-shaping input that affects stored chunks/vectors match the existing indexed version.

Index-shaping identity SHALL cover at least effective embedding provider/model, parser/document backend where relevant, and chunking configuration/strategy that affects emitted text boundaries. A content-only hash SHALL NOT cause stale vectors/chunks to be reused after these values change.

#### Scenario: Same bytes and same index identity
- **GIVEN** a previously indexed file whose content and index-shaping identity are unchanged
- **WHEN** the same path is ingested again
- **THEN** parse, chunk, embed and store-write work SHALL be skipped for that file

#### Scenario: Same bytes but embedding model changes
- **GIVEN** the source bytes are unchanged
- **BUT** the effective embedding model differs from the stored index identity
- **WHEN** ingestion runs
- **THEN** the file MUST be reprocessed rather than skipped

#### Scenario: Same bytes but parser or chunk settings change
- **GIVEN** the source bytes are unchanged
- **BUT** parser/document backend or chunk-shaping settings differ
- **WHEN** ingestion runs
- **THEN** the file MUST be reprocessed

### Requirement: Replacement preserves the last durable searchable version on failure

Updating an already-indexed source SHALL NOT delete the last durable searchable version merely because a later parse, chunk, embedding or store-write step fails. New-version rows SHALL become durable and be verified before stale-version rows are removed, or another store-neutral mechanism SHALL provide the same safety property.

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

### Requirement: Ingestion exposes stage timing without changing correctness

The pipeline SHALL expose enough internal timing/diagnostic data for experiments to distinguish parse/chunk, embedding, store write, lock wait and total time. Instrumentation SHALL NOT change ordering or error semantics.

#### Scenario: Performance experiment
- **WHEN** the bounded-ingestion experiment runs
- **THEN** it MUST be able to attribute wall time to parse/chunk, embedding and store-write stages rather than reporting only one undifferentiated total

### Requirement: Concurrency optimisation follows evidence

The correctness implementation SHALL not claim that `embed_concurrency` provides concurrent file-level embedding unless the measured implementation actually allows it. If a later optimisation moves embedding outside a narrow mutation lock, tests SHALL prove replacement safety, store mutation safety and generation correctness remain intact.

#### Scenario: Configured concurrency is not effective
- **GIVEN** the current lock structure serialises the full embed+write operation
- **WHEN** diagnostics describe effective ingestion concurrency
- **THEN** the system MUST NOT report multiple concurrent file-level embedding jobs merely because the configured integer is greater than one
