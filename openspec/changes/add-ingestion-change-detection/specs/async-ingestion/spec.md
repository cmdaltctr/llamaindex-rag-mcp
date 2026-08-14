## ADDED Requirements

### Requirement: Ingestion skips unchanged files

When `ingest_path_async` is called on a path whose files have been previously
ingested into the target collection, the system SHALL compute a SHA-256 hash
of each eligible non-binary file's content and compare it against the
`source_content_hash` stored in every chunk for that `file_path`. A file SHALL
be skipped entirely only when at least one chunk exists and every matching
chunk has a non-null hash equal to the computed hash: no chunk deletion,
re-chunking, re-embedding, or metadata extraction SHALL run for that file.
Files with different, missing, or mixed hashes and files with no existing
chunks SHALL be ingested normally. Binary files SHALL retain the existing
`status: "skipped"` behaviour and SHALL NOT participate in change detection.

#### Scenario: Unchanged file is skipped on re-ingest

- **WHEN** a directory containing one file is ingested into a collection
- **AND** `ingest_path_async` is called again on the same directory and
  collection with the file unmodified
- **THEN** the file SHALL NOT be re-chunked or re-embedded
- **THEN** the collection's chunk count for that file SHALL remain unchanged

#### Scenario: Modified file is re-ingested

- **WHEN** a previously ingested file is modified on disk
- **AND** `ingest_path_async` is called on the same path and collection
- **THEN** the file's previous chunks SHALL be deleted
- **THEN** the file SHALL be re-chunked and re-embedded
- **THEN** the stored content hash for the file SHALL be updated to the new
  hash

#### Scenario: Legacy chunks without a stored hash are re-ingested once

- **WHEN** `ingest_path_async` runs against a collection persisted before
  content hashing existed (chunks carry no content-hash metadata)
- **THEN** all eligible non-binary files SHALL be re-ingested on that call
- **THEN** the re-ingested chunks SHALL carry `source_content_hash`
- **AND** a subsequent call with no file changes SHALL skip all eligible
  non-binary files

#### Scenario: Mixed directory skips only unchanged files

- **WHEN** a directory contains three previously ingested eligible non-binary
  files and exactly one has been modified
- **AND** `ingest_path_async` is called on the directory
- **THEN** only the modified file SHALL be re-ingested
- **THEN** the two unchanged files SHALL be skipped

#### Scenario: Mixed or missing chunk hashes force re-ingestion

- **WHEN** a file's existing chunks contain mixed hashes or a missing
  `source_content_hash`
- **AND** `ingest_path_async` is called with that file unmodified
- **THEN** the file SHALL be re-ingested
- **THEN** every replacement chunk SHALL carry the current hash

#### Scenario: Hash-read failure does not abort sibling files

- **WHEN** `sha256_file` raises `FileNotFoundError` or `OSError` for one file
  in a multi-file ingestion
- **THEN** that file SHALL be reported in `file_details` with
  `status: "failed"` and `chunks: 0`
- **THEN** its existing chunks SHALL remain untouched
- **AND** ingestion SHALL continue for the sibling files

#### Scenario: Binary files retain the existing skip behaviour

- **WHEN** a discovered supported-extension file is detected as binary
- **THEN** the file SHALL appear in `file_details` with `status: "skipped"`
- **THEN** the file SHALL NOT contribute to `files_skipped_unchanged`

### Requirement: Content hash stored in chunk metadata

For every ingested file, the system SHALL store the file's SHA-256 content
hash as `source_content_hash` in the ChromaDB metadata of every chunk belonging
to that file. Hash stamping SHALL occur whether `skip_unchanged` is `true` or
`false`. The field SHALL be additive: existing metadata fields (including
`file_path`) SHALL retain their names and types. A file whose content changes
between two ingests SHALL have every chunk's stored hash replaced with the new
hash.

#### Scenario: Chunks carry the content hash after ingest

- **WHEN** a supported non-binary file is ingested into a collection
- **THEN** every chunk written for that file SHALL include
  `source_content_hash` whose value is the SHA-256 hex digest of the file's
  bytes at ingest time

#### Scenario: Hash reflects the latest ingest

- **WHEN** a file is modified and re-ingested
- **THEN** the stored hash on all of the file's chunks SHALL equal the hash
  of the new content
- **THEN** no chunk SHALL retain the previous hash

### Requirement: Ingestion result reports skipped files

The ingestion result dict SHALL report skipped files additively. The result
SHALL carry a top-level `files_skipped_unchanged` integer counting eligible
non-binary files skipped by change detection. Each file skipped by change
detection SHALL appear in `file_details` with `status: "skipped_unchanged"`
and `chunks: 0`. This status is distinct from the existing `"skipped"` status
for unsupported-extension and binary files. All existing result keys
(`status`, `files_indexed`, `chunks_created`, `chunks_removed`, `collection`,
`file_details`, `metadata_degraded`, `warnings`) and all existing
`file_details` keys SHALL retain their current names and types. Skipped files
SHALL NOT be counted in `files_indexed`, and their chunks SHALL NOT be counted
in `chunks_removed`.

#### Scenario: Fully unchanged directory reports all files skipped

- **WHEN** `ingest_path_async` is called on a directory where every eligible
  non-binary file is unchanged since the previous ingest into the collection
- **THEN** the result dict SHALL contain `files_skipped_unchanged` equal to
  the number of eligible non-binary files
- **THEN** `files_indexed` SHALL be `0` and `chunks_created` SHALL be `0`
- **THEN** the result `status` SHALL be `"ok"`

#### Scenario: Partially changed directory reports mixed counts

- **WHEN** three eligible non-binary files with one modified are ingested
- **THEN** `files_skipped_unchanged` SHALL be `2` and `files_indexed` SHALL
  be `1`
- **THEN** exactly two `file_details` entries SHALL have
  `status: "skipped_unchanged"`

#### Scenario: Existing result keys are unchanged

- **WHEN** any ingestion completes with change detection active
- **THEN** the result dict SHALL retain all existing keys with their
  existing types
- **THEN** `files_skipped_unchanged` SHALL be present and SHALL be `0` when
  no file was skipped

### Requirement: Change detection can be disabled per call

The system SHALL expose a `skip_unchanged` ingestion setting, configurable
via the nested environment variable `INGESTION__SKIP_UNCHANGED` with default
`true`. When set to `false`, `ingest_path_async` SHALL re-ingest every
eligible non-binary file regardless of stored hashes, while still stamping
every chunk with the current `source_content_hash`. This covers forced
re-embeds after changing the embedding model or chunking parameters, which
alter desired vectors without altering file content.

#### Scenario: Opt-out forces full re-ingest

- **WHEN** `INGESTION__SKIP_UNCHANGED=false` is set
- **AND** `ingest_path_async` is called on an unchanged, previously ingested
  directory
- **THEN** every eligible non-binary file SHALL be re-chunked and re-embedded
- **THEN** `files_skipped_unchanged` SHALL be `0`

#### Scenario: Default leaves change detection active

- **WHEN** no `INGESTION__SKIP_UNCHANGED` value is configured
- **THEN** change detection SHALL be active (behaviour identical to `true`)
