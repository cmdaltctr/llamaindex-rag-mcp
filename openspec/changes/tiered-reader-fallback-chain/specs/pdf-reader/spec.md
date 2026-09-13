## MODIFIED Requirements

### Requirement: pdf-inspector silent-empty extraction SHALL recover via a plain-text retry

When the pdf-inspector reader classifies a PDF as `text_based` while its own Markdown extraction is empty and the page count is greater than zero, the adapter SHALL retry the file with the registered `liteparse` reader in extraction-only mode (OCR disabled regardless of operator settings), joining the per-page text into one document for the whole file, so a readable text layer is not silently discarded. When liteparse is unavailable or its retry yields no text, the adapter SHALL retry with the registered `pypdf` reader, preserving the same one-document contract.

A successful retry SHALL correct the routing evidence it emits: the scalar `pages_needing_ocr` SHALL be set to zero, because the pages were flagged only by the failed extraction, and the pre-fallback flagged count SHALL be preserved under an additive diagnostic key. A retry chain that yields no text from either tier SHALL leave the original pdf-inspector result unchanged so the OCR routing gate still sees the flagged evidence. Diagnostics SHALL be additive, and `extraction_fallback_backend` SHALL name the tier that produced the text (`liteparse` or `pypdf`); diagnostics SHALL NOT claim the OCR worker or any other backend produced it.

#### Scenario: Contradiction triggers the retry

- **GIVEN** pdf-inspector returns `pdf_type=text_based`, non-zero `page_count`, and empty Markdown
- **WHEN** the adapter emits its document
- **THEN** the document text SHALL be the joined liteparse per-page extraction
- **AND** the document SHALL carry an additive diagnostic naming liteparse as the fallback backend

#### Scenario: liteparse unavailable falls through to pypdf

- **GIVEN** the contradiction triggers and the liteparse package is not installed, or its retry raises or yields no text
- **WHEN** the adapter emits its document
- **THEN** the retry SHALL proceed with the registered pypdf reader
- **AND** the diagnostic SHALL name pypdf as the fallback backend when it produces the text

#### Scenario: Recovered text corrects the routing evidence

- **GIVEN** a fallback tier recovers text from a file pdf-inspector flagged page-by-page
- **WHEN** the OCR routing seam reads the emitted metadata
- **THEN** `pages_needing_ocr` SHALL be zero
- **AND** the original flagged count SHALL be preserved under a separate diagnostic key

#### Scenario: Failed retry keeps the original evidence

- **GIVEN** both fallback tiers yield no text
- **WHEN** the adapter emits its document
- **THEN** the emitted result SHALL be the unchanged pdf-inspector result with its original flagged count
- **AND** the OCR routing decision SHALL be unchanged from a run without the guard

#### Scenario: Normal extraction is untouched

- **GIVEN** pdf-inspector returns non-empty Markdown for a `text_based` PDF
- **WHEN** the adapter emits its document
- **THEN** no retry SHALL occur
- **AND** the metadata SHALL carry no fallback diagnostics

#### Scenario: Scanned classifications are untouched

- **GIVEN** pdf-inspector classifies a PDF as `scanned`, `image_based`, or another non-`text_based` type
- **WHEN** the adapter emits its document
- **THEN** no retry SHALL occur regardless of extraction emptiness
- **AND** the OCR routing decision SHALL be unchanged
