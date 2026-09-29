## ADDED Requirements

### Requirement: pdf-inspector OCR evidence SHALL cover every page of text_based PDFs longer than the detection sample

pdf-inspector detects OCR need from a bounded page sample (8 pages). When `process_pdf` classifies a PDF as `text_based` and its page count is greater than 8, the adapter SHALL compute `pages_needing_ocr` from a scan of every page (`extract_pages_markdown`), so image-only pages outside the sample reach the OCR routing gate. The adapter SHALL NOT change `pdf_type`, `pdf_confidence` or the extracted Markdown, and SHALL NOT add a metadata key.

#### Scenario: Image-only page outside the sample is counted

- **GIVEN** a 20-page PDF that pdf-inspector classifies as `text_based` with no sampled page needing OCR
- **AND** a full page scan finds 3 pages needing OCR
- **WHEN** the adapter emits its document
- **THEN** `pages_needing_ocr` SHALL be 3

#### Scenario: Short or already complete results get no extra scan

- **GIVEN** a `text_based` PDF with 8 pages or fewer, or a PDF classified `scanned`, `image_based` or `mixed`
- **WHEN** the adapter emits its document
- **THEN** no full page scan SHALL run

#### Scenario: Full scan failure keeps the sampled evidence

- **GIVEN** a `text_based` PDF longer than 8 pages whose full page scan raises
- **WHEN** the adapter emits its document
- **THEN** `pages_needing_ocr` SHALL be the sampled count
- **AND** the read SHALL succeed with a logged warning

#### Scenario: Silent-empty rescue records the full-scan count

- **GIVEN** a `text_based` PDF longer than 8 pages with empty Markdown whose fallback tier recovers text
- **WHEN** the adapter emits its document
- **THEN** `pages_needing_ocr` SHALL be zero
- **AND** `pages_needing_ocr_before_fallback` SHALL be the full-scan count
