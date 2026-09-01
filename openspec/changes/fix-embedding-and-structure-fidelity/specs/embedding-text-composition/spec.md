## ADDED Requirements

### Requirement: Embedding text is a declared contract

The system SHALL treat the text sent to the embedding model as an explicit
contract rather than a by-product of which reader ran. Exactly one module
SHALL own the set of metadata keys excluded from embedding text, and it SHALL
apply that set to every node on every ingest path.

Keys SHALL be excluded when they are machine identity, parser telemetry, or
filesystem bookkeeping — values that are constant within a document and carry
no retrievable meaning. Keys SHALL be retained when they carry topical signal
a query could plausibly match.

#### Scenario: Parser telemetry never reaches the embedding model

- **WHEN** a PDF is ingested with any configured reader
- **THEN** the text passed to the embedding model MUST NOT contain
  `pdf_reader`, `pdf_type`, `pdf_confidence`, `page_count`, `page`,
  `page_label`, `column`, `section_bbox`, or `bbox_schema_version`
- **AND** the chunk's own text MUST be present unchanged

#### Scenario: Filesystem bookkeeping never reaches the embedding model

- **WHEN** any file is ingested
- **THEN** the text passed to the embedding model MUST NOT contain
  `file_path`, `file_type`, `file_size`, `creation_date`,
  `last_modified_date`, or `last_accessed_date`
- **AND** it MUST still contain `file_name`, which carries topical signal

#### Scenario: Extracted metadata is retained

- **WHEN** metadata extraction produced `category`, `keywords`, `summary`, or
  `document_title`
- **THEN** those values MUST remain in the embedding text
- **AND** `header_path`, when present, MUST remain in the embedding text

#### Scenario: Exclusion is applied on every path

- **WHEN** nodes are produced by the code, config, structured-backend, or
  document chunking path
- **THEN** the same exclusion set MUST be applied to all of them

### Requirement: The exclusion set participates in index identity

The system SHALL include a fingerprint of the embedding-text exclusion set in
`source_index_identity`, so that changing which keys are embedded invalidates
previously written chunks exactly as a chunk-size or embedding-model change
does.

#### Scenario: Changing the exclusion set forces reprocessing

- **WHEN** the exclusion set changes and a previously indexed, byte-identical
  source is ingested again
- **THEN** the source MUST NOT be reported as `skipped_unchanged`
- **AND** it MUST be re-chunked, re-embedded, and replaced through the
  existing failure-safe replacement path

#### Scenario: An unchanged exclusion set does not force reprocessing

- **WHEN** the exclusion set is unchanged and a byte-identical source is
  ingested again under identical settings
- **THEN** the source MUST be reported as `skipped_unchanged`

### Requirement: Stored text is unaffected

Excluding a key from embedding text SHALL NOT remove it from stored metadata,
from retrieval results, or from the stored chunk text.

#### Scenario: Metadata survives exclusion

- **WHEN** a chunk whose `file_path` is excluded from embedding text is
  retrieved
- **THEN** the result row MUST still expose `file_path` in its metadata and
  MUST still populate the `source` field from it
