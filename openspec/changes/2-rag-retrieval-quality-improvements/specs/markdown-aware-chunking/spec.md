## ADDED Requirements

### Requirement: Markdown files use heading-aware chunking with a size cap
The system SHALL chunk files with extension `.md` using a heading-aware node parser chained with a sentence splitter capped at `CHUNK_SIZE`. Heading boundaries SHALL be respected wherever the heading-bounded section is at most `CHUNK_SIZE` characters; sections longer than `CHUNK_SIZE` SHALL be further split by the sentence splitter so that no produced chunk exceeds `CHUNK_SIZE`. Non-Markdown files SHALL retain the existing splitter behaviour.

#### Scenario: Markdown headings remain intact when sections fit
- **GIVEN** a Markdown document with multiple `##` sections, each shorter than `CHUNK_SIZE`
- **WHEN** the document is ingested
- **THEN** chunk boundaries SHALL align with heading boundaries
- **THEN** no chunk SHALL contain a partial heading line followed by unrelated section text

#### Scenario: Long heading-bounded section is further split
- **GIVEN** a Markdown document whose single `##` section text exceeds `CHUNK_SIZE`
- **WHEN** the document is ingested
- **THEN** that section SHALL be split into more than one chunk
- **THEN** every produced chunk SHALL have length at most `CHUNK_SIZE` (within the splitter's tokenisation tolerance)

#### Scenario: Non-Markdown files are unchanged
- **GIVEN** a `.txt` or `.pdf` file
- **WHEN** the file is ingested
- **THEN** chunking SHALL use the existing default splitter
- **THEN** the chunk count and content SHALL match the previous default behaviour for the same file

#### Scenario: Markdown without headings still chunks
- **GIVEN** a `.md` file with no headings
- **WHEN** the file is ingested
- **THEN** chunking SHALL still produce non-empty chunks
- **THEN** ingestion SHALL succeed without raising
