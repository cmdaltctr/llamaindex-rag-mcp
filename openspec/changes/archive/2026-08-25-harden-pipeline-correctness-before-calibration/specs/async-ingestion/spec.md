## ADDED Requirements

### Requirement: Directory ingestion has bounded in-memory node lifetime

`ingest_path_async()` SHALL NOT retain every emitted node for an arbitrarily large directory before the first write. The pipeline SHALL process and persist explicitly bounded units, with one source file at a time as the minimum acceptable bound unless a smaller batch is required for a single large file.

#### Scenario: Corpus size increases by file count
- **GIVEN** a generated corpus of many independent files
- **WHEN** the corpus is ingested
- **THEN** the number of simultaneously retained source-file node sets MUST remain bounded independently of total file count
- **AND** successful earlier files MAY become durable before later files have been parsed

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

## MODIFIED Requirements

### Requirement: Unchanged files skip expensive reprocessing using complete index identity

The ingestion pipeline SHALL persist a source-content identity and an index-shaping identity for each stored source version. A file MAY be skipped as unchanged only when its content identity and every index-shaping input that affects stored chunks/vectors match the existing indexed version.

Index-shaping identity SHALL cover at least effective embedding provider/model, parser/document backend where relevant, and chunking configuration/strategy that affects emitted text boundaries. A content-only hash SHALL NOT cause stale vectors/chunks to be reused after these values change. Files with different, missing, or mixed identities and files with no existing chunks SHALL be ingested normally. Binary files SHALL retain the existing `status: "skipped"` behaviour and SHALL NOT participate in change detection.

#### Scenario: Same bytes and same index identity
- **GIVEN** a previously indexed file whose content and index-shaping identity are unchanged
- **WHEN** the same path is ingested again
- **THEN** parse, chunk, embed and store-write work SHALL be skipped for that file

#### Scenario: Unchanged file is skipped on re-ingest
- **WHEN** a directory containing one file is ingested into a collection
- **AND** `ingest_path_async` is called again on the same directory and collection with the file unmodified and the index-shaping inputs unchanged
- **THEN** the file SHALL NOT be re-chunked or re-embedded
- **THEN** the collection's chunk count for that file SHALL remain unchanged

#### Scenario: File with no stored chunks is ingested
- **WHEN** an eligible non-binary file has no existing chunks in the target collection (never ingested, or its previous ingest produced zero chunks)
- **AND** `ingest_path_async` is called on its path
- **THEN** the file SHALL be ingested normally
- **AND** the file SHALL NOT be classified as `skipped_unchanged`

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

#### Scenario: Modified file is re-ingested
- **WHEN** a previously ingested file is modified on disk
- **AND** `ingest_path_async` is called on the same path and collection
- **THEN** the file's previous chunks SHALL be deleted
- **THEN** the file SHALL be re-chunked and re-embedded
- **THEN** the stored source and index identities for the file SHALL be updated

#### Scenario: Legacy chunks without a stored hash are re-ingested once
- **WHEN** `ingest_path_async` runs against a collection persisted before content hashing existed (chunks carry no content-hash metadata)
- **THEN** all eligible non-binary files SHALL be re-ingested on that call
- **THEN** the re-ingested chunks SHALL carry `source_content_hash`
- **AND** a subsequent call with no file or index-shaping changes SHALL skip all eligible non-binary files

#### Scenario: Mixed directory skips only unchanged files
- **WHEN** a directory contains three previously ingested eligible non-binary files and exactly one has been modified
- **AND** `ingest_path_async` is called on the directory
- **THEN** only the modified file SHALL be re-ingested
- **THEN** the two unchanged files SHALL be skipped

#### Scenario: Mixed or missing chunk hashes force re-ingestion
- **WHEN** a file's existing chunks contain mixed hashes or a missing `source_content_hash`
- **AND** `ingest_path_async` is called with that file unmodified
- **THEN** the file SHALL be re-ingested
- **THEN** every replacement chunk SHALL carry the current hash

#### Scenario: Hash-read failure does not abort sibling files
- **WHEN** `sha256_file` raises `FileNotFoundError` or `OSError` for one file in a multi-file ingestion
- **THEN** that file SHALL be reported in `file_details` with `status: "failed"` and `chunks: 0`
- **THEN** its existing chunks SHALL remain untouched
- **AND** ingestion SHALL continue for the sibling files

#### Scenario: Binary files retain the existing skip behaviour
- **WHEN** a discovered supported-extension file is detected as binary
- **THEN** the file SHALL appear in `file_details` with `status: "skipped"`
- **THEN** the file SHALL NOT contribute to `files_skipped_unchanged`
