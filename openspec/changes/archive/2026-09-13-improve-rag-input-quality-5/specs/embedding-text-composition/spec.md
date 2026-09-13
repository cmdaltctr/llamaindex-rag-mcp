## MODIFIED Requirements

### Requirement: Embedding text is a declared contract

The system SHALL treat the text sent to the embedding model as an explicit
contract rather than a by-product of which reader ran. Exactly one module
SHALL own the set of metadata keys excluded from embedding text, and it SHALL
apply that set to every node on every ingest path.

Keys SHALL be excluded when they are machine identity, parser telemetry, or
filesystem bookkeeping — values that are constant within a document and carry
no retrievable meaning. Keys SHALL be retained when they carry topical signal
a query could plausibly match.

The OCR diagnostics this change adds — `ocr_required`, `ocr_used`,
`ocr_backend`, and `pages_needing_ocr` — are parser telemetry by that test:
each is constant across every chunk of a document and none carries signal a
user query could match. They SHALL join the same centrally owned exclusion set
rather than a second list held by the PDF reader.

#### Scenario: Parser telemetry never reaches the embedding model

- **WHEN** a PDF is ingested with any configured reader
- **THEN** the text passed to the embedding model MUST NOT contain
  `pdf_reader`, `pdf_type`, `pdf_confidence`, `page_count`, `page`,
  `page_label`, `column`, `section_bbox`, or `bbox_schema_version`
- **AND** the chunk's own text MUST be present unchanged

#### Scenario: OCR diagnostics never reach the embedding model

- **WHEN** a PDF is ingested through either the `pdf-inspector` fast path or
  the OCR fallback
- **THEN** the text passed to the embedding model MUST NOT contain
  `ocr_required`, `ocr_used`, `ocr_backend`, or `pages_needing_ocr`
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

### Requirement: Stored text is unaffected

Excluding a key from embedding text SHALL NOT remove it from stored metadata,
from retrieval results, or from the stored chunk text.

#### Scenario: Metadata survives exclusion

- **WHEN** a chunk whose `file_path` is excluded from embedding text is
  retrieved
- **THEN** the result row MUST still expose `file_path` in its metadata and
  MUST still populate the `source` field from it

#### Scenario: OCR diagnostics survive exclusion

- **WHEN** a chunk from a PDF that required OCR is retrieved
- **THEN** the result row MUST still expose `ocr_required`, `ocr_used`, and
  `ocr_backend` in its metadata
- **AND** `pages_needing_ocr` MUST still be exposed as a store-compatible
  scalar value
- **AND** an operator MUST be able to tell from those values whether the
  chunk came from the fast path, the OCR fallback, or a degraded extraction
