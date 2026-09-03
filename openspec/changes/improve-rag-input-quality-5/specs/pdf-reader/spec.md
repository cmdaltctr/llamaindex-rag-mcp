## ADDED Requirements

### Requirement: pdf-inspector SHALL route OCR-required PDFs to an optional document-understanding fallback

When the configured PDF path uses `pdf_inspector`, the system SHALL use the existing `pdf-inspector` result as both the fast extraction result and the evidence for deciding whether OCR/document understanding is required. Text-based PDFs with acceptable extraction quality SHALL keep the `pdf-inspector` Markdown. PDFs classified as scanned, image-based, or mixed, PDFs with material `pages_needing_ocr`, or PDFs that fail a separately calibrated extraction-quality gate SHALL be eligible for the OCR fallback when that capability is available.

Layout complexity alone SHALL NOT require OCR. A text-based multi-column or table-heavy PDF that `pdf-inspector` extracts acceptably SHALL remain on the fast path.

The first implementation SHALL route the whole PDF to the fallback when the OCR condition is met; it SHALL NOT merge page fragments from two PDF engines.

#### Scenario: Clean text-based PDF stays on pdf-inspector

- **GIVEN** `pdf_inspector` is the configured PDF path and PaddleOCR is available
- **AND** `pdf-inspector` classifies the PDF as text-based with acceptable extraction quality and no material OCR requirement
- **WHEN** the PDF is ingested
- **THEN** the `pdf-inspector` Markdown SHALL be used
- **AND** PaddleOCR SHALL NOT be invoked

#### Scenario: Complex text layout does not imply OCR

- **GIVEN** a text-based PDF containing multiple columns or tables
- **AND** `pdf-inspector` extracts the layout with acceptable quality
- **WHEN** the PDF is ingested
- **THEN** the PDF SHALL remain on the `pdf-inspector` path
- **AND** layout complexity alone SHALL NOT invoke PaddleOCR

#### Scenario: Scanned or image-based PDF uses the OCR fallback

- **GIVEN** `pdf-inspector` classifies a PDF as scanned or image-based
- **AND** the PaddleOCR capability is available
- **WHEN** the PDF is ingested
- **THEN** the whole PDF SHALL be parsed by the PaddleOCR fallback
- **AND** the Paddle result SHALL replace the partial `pdf-inspector` extraction as the downstream document text

#### Scenario: Mixed PDF with material OCR requirement uses the fallback

- **GIVEN** `pdf-inspector` reports mixed content or material `pages_needing_ocr`
- **AND** the configured routing gate selects OCR
- **AND** the PaddleOCR capability is available
- **WHEN** the PDF is ingested
- **THEN** the whole PDF SHALL be parsed by PaddleOCR
- **AND** the system SHALL NOT stitch independently parsed page fragments from the two engines

#### Scenario: OCR required but optional capability is absent

- **GIVEN** `pdf-inspector` reports that OCR is required
- **AND** the optional PaddleOCR capability is not installed or cannot be resolved
- **WHEN** the PDF is ingested
- **THEN** the system SHALL retain the available `pdf-inspector` Markdown rather than fabricate missing content
- **AND** the document/file result SHALL report that OCR was required but unavailable
- **AND** ingestion SHALL remain within the existing per-file error/degradation boundary

### Requirement: The PaddleOCR fallback SHALL use a full document parsing pipeline

The OCR fallback SHALL use the supported PaddleOCR-VL document pipeline, including its layout/region processing, reading-order handling, recognition, and result assembly. The implementation SHALL NOT treat the VLM checkpoint as a bare whole-page string OCR call when the pipeline can preserve document structure.

The Paddle adapter SHALL emit structured Markdown suitable for the same downstream Markdown chunking path used by `pdf-inspector` output.

#### Scenario: Paddle result preserves structured document elements

- **GIVEN** an OCR-required PDF containing headings, paragraphs, and a table
- **WHEN** PaddleOCR successfully parses the document
- **THEN** the emitted text SHALL be Markdown
- **AND** structural elements available from the parser SHALL be represented in that Markdown rather than flattened into an undifferentiated text stream

#### Scenario: Paddle dependency is lazy and optional

- **GIVEN** a base installation that does not include the optional OCR dependency group
- **WHEN** the package starts and processes non-OCR content
- **THEN** PaddleOCR, PaddleX, and PaddlePaddle SHALL NOT be required on the base import path
- **AND** the server SHALL remain usable for the existing non-OCR paths

### Requirement: PDF extraction branches SHALL converge on one structured-Markdown contract

Both successful `pdf-inspector` extraction and successful PaddleOCR fallback SHALL provide downstream ingestion with Markdown plus honest metadata. Existing source/provenance metadata SHALL be preserved. OCR-specific metadata SHALL be additive and SHALL NOT overwrite more authoritative existing values.

The change SHALL NOT require a new canonical document class or a second chunking pipeline.

#### Scenario: Fast and OCR paths enter the same Markdown chunking branch

- **GIVEN** one PDF succeeds through `pdf-inspector` and another succeeds through PaddleOCR
- **WHEN** their reader results reach document chunking
- **THEN** both SHALL declare or otherwise carry Markdown as their emitted text format
- **AND** both SHALL be eligible for the same Markdown chunking strategy

#### Scenario: OCR diagnostics are honest

- **WHEN** a PDF result is emitted
- **THEN** metadata SHALL make it possible to distinguish whether OCR was required and whether OCR was actually used
- **AND** a result produced only by `pdf-inspector` SHALL NOT claim that PaddleOCR processed the document
