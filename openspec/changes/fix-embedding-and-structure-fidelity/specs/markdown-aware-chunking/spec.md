## MODIFIED Requirements

### Requirement: Markdown files use heading-aware chunking with a size cap

The system SHALL chunk Markdown text using a heading-aware node parser chained
with a sentence splitter capped at `CHUNKING__MARKDOWN_CHUNK_SIZE`. Text
counts as Markdown when the source file has extension `.md`, **or** when the
reader that produced it declares its emitted text format as `markdown`.
Heading boundaries SHALL be respected wherever the heading-bounded section is
at most `CHUNKING__MARKDOWN_CHUNK_SIZE` characters; sections longer than
`CHUNKING__MARKDOWN_CHUNK_SIZE` SHALL be further split by the sentence splitter
so that no produced chunk exceeds `CHUNKING__MARKDOWN_CHUNK_SIZE` within the
splitter's tokenisation tolerance. Text from readers declaring `plain` SHALL
retain the existing splitter behaviour and global `CHUNKING__CHUNK_SIZE`
default.

This replaces the previous rule, which selected the heading-aware path from
the source file's extension alone and therefore discarded Markdown structure
produced by a reader from a non-Markdown source.

#### Scenario: Markdown headings remain intact when sections fit

- **GIVEN** a Markdown document with multiple `##` sections, each shorter than `CHUNKING__MARKDOWN_CHUNK_SIZE`
- **WHEN** the document is ingested
- **THEN** chunk boundaries SHALL align with heading boundaries
- **THEN** no chunk SHALL contain a partial heading line followed by unrelated section text

#### Scenario: Long heading-bounded section is further split

- **GIVEN** a Markdown document whose single `##` section text exceeds `CHUNKING__MARKDOWN_CHUNK_SIZE`
- **WHEN** the document is ingested
- **THEN** that section SHALL be split into more than one chunk
- **THEN** every produced chunk SHALL have length at most `CHUNKING__MARKDOWN_CHUNK_SIZE` within the splitter's tokenisation tolerance

#### Scenario: Non-Markdown files are unchanged

- **GIVEN** a `.txt` file, or a `.pdf` read by a reader declaring `plain`
- **WHEN** the file is ingested
- **THEN** chunking SHALL use the existing default splitter
- **THEN** the chunk count and content SHALL match the previous default behaviour for the same file
- **THEN** no `header_path` SHALL be fabricated

  Note: this scenario is narrowed, not dropped. Previously every `.pdf` was
  non-Markdown by definition; now a `.pdf` read by a Markdown-declaring reader
  takes the heading-aware path, covered by the scenario below.

#### Scenario: Markdown-format reader output uses the heading-aware path

- **GIVEN** a `.pdf` read by a reader declaring its emitted text format as `markdown`
- **WHEN** the file is ingested
- **THEN** the heading-aware node parser SHALL run before sentence splitting
- **THEN** the emitted chunks SHALL carry `header_path`
- **THEN** the `CHUNKING__MARKDOWN_CHUNK_SIZE` budget SHALL apply

#### Scenario: Markdown without headings still chunks

- **GIVEN** a `.md` file with no headings
- **WHEN** the file is ingested
- **THEN** chunking SHALL still produce non-empty chunks
- **THEN** ingestion SHALL succeed without raising

#### Scenario: Reader-produced Markdown honours the recovery knobs

- **GIVEN** reader-produced Markdown text
- **WHEN** the file is ingested
- **THEN** `ensure_heading_metadata`, `apply_heading_prepend` and
  `drop_small_markdown_chunks` SHALL apply with the same configured behaviour
  they have for `.md` files
