## ADDED Requirements

### Requirement: Readers declare their emitted text format

Each registered PDF reader SHALL declare the text format it emits and whether
it provides page-level provenance as registry metadata, alongside its existing
import path and dependency probe. Downstream consumers SHALL route on the text
format declaration rather than inferring format from the source file's
extension, and SHALL be able to report the page capability.

#### Scenario: Declared formats

- **WHEN** the PDF reader registry is inspected
- **THEN** `pdf_inspector` MUST declare `markdown`
- **AND** `liteparse`, `pypdf`, and `pypdfium2` MUST declare `plain`

#### Scenario: A new reader must declare a format

- **WHEN** a reader is registered without a text-format declaration
- **THEN** registration MUST fail rather than defaulting silently

### Requirement: Page provenance is honest per reader

Readers that can observe page boundaries SHALL emit `page_label`, the key
retrieval reads. Readers that cannot SHALL emit nothing rather than a
placeholder, and the system SHALL NOT promise the field where it cannot be
produced.

#### Scenario: liteparse emits page_label

- **WHEN** a PDF is parsed by `liteparse`
- **THEN** each emitted document MUST carry `page_label` as a string
  alongside the existing integer `page`
- **AND** a chunk retrieved from that document MUST return a non-null
  `page_label`

#### Scenario: pypdfium2 emits page_label

- **WHEN** a PDF is parsed by `pypdfium2`
- **THEN** each emitted page document MUST carry `page_label` as a string
  alongside the existing integer `page`
- **AND** a chunk retrieved through the `auto` chain MUST preserve it

#### Scenario: pdf_inspector reports no page

- **WHEN** a PDF is parsed by `pdf_inspector`, which returns one document for
  the whole file
- **THEN** `page_label` MUST be absent rather than fabricated
- **AND** the reader MUST continue to report `page_count` in metadata so an
  operator can see the document's true length

#### Scenario: Page support is discoverable

- **WHEN** an operator or caller inspects the configured reader through the
  registry descriptor
- **THEN** the descriptor MUST report whether page-level provenance is
  available under that configuration
