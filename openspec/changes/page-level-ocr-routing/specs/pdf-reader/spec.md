## MODIFIED Requirements

### Requirement: pdf-inspector SHALL route OCR-required PDFs to an isolated document-understanding worker

When the configured PDF path uses `pdf_inspector`, the system SHALL use the existing `pdf-inspector` result as both the fast extraction result and the evidence for deciding whether OCR/document understanding is required. Text-based PDFs with acceptable extraction quality SHALL keep the `pdf-inspector` Markdown. When the isolated worker capability is available and OCR is enabled, scanned and image-based PDFs SHALL route unconditionally. Other types, including mixed PDFs, SHALL route only when a positive configured threshold condition is met. A confidence below the minimum or an OCR-page proportion at or above the configured fraction SHALL select OCR. A zero threshold SHALL disable its condition.

Layout complexity alone SHALL NOT require OCR. A text-based multi-column or table-heavy PDF that `pdf-inspector` extracts acceptably SHALL remain on the fast path.

With the `document` routing unit (the default), the system SHALL route the whole PDF to the worker when the OCR condition is met and SHALL NOT merge page fragments from two PDF engines. With the `page` routing unit, routing SHALL follow the page-level OCR routing requirement instead.

#### Scenario: Clean text-based PDF stays on pdf-inspector without starting the parsing worker

- **GIVEN** `pdf_inspector` is the configured PDF path and the OCR worker is available
- **AND** `pdf-inspector` classifies the PDF as text-based with acceptable extraction quality and no material OCR requirement
- **WHEN** the PDF is ingested
- **THEN** the `pdf-inspector` Markdown SHALL be used
- **AND** no OCR parse request SHALL be dispatched
- **AND** the long-lived worker and its model SHALL NOT be started

#### Scenario: Complex text layout does not imply OCR

- **GIVEN** a text-based PDF containing multiple columns or tables
- **AND** `pdf-inspector` extracts the layout with acceptable quality
- **WHEN** the PDF is ingested
- **THEN** the PDF SHALL remain on the `pdf-inspector` path
- **AND** layout complexity alone SHALL NOT start or invoke the OCR worker

#### Scenario: Scanned or image-based PDF uses the OCR worker

- **GIVEN** `pdf-inspector` classifies a PDF as scanned or image-based
- **AND** the capability probe reports that the isolated OCR worker is available and compatible
- **WHEN** the PDF is ingested
- **THEN** the whole PDF SHALL be parsed by the PaddleOCR-VL worker
- **AND** the worker result SHALL replace the partial `pdf-inspector` extraction as the downstream document text

#### Scenario: Mixed PDF with material OCR requirement uses the worker

- **GIVEN** the `document` routing unit is configured
- **AND** `pdf-inspector` reports mixed content or material `pages_needing_ocr`
- **AND** the configured routing gate selects OCR
- **AND** the capability probe reports that the isolated OCR worker is available and compatible
- **WHEN** the PDF is ingested
- **THEN** the whole PDF SHALL be parsed by the PaddleOCR-VL worker
- **AND** the system SHALL NOT stitch independently parsed page fragments from the two engines

#### Scenario: Mixed PDF with zero thresholds stays on the fast path

- **GIVEN** OCR is enabled and a PDF is classified as mixed
- **AND** both routing thresholds are zero
- **WHEN** the PDF is ingested
- **THEN** no OCR parse request SHALL be dispatched
- **AND** the existing extracted Markdown and page diagnostics SHALL be preserved

#### Scenario: OCR required but the worker is unavailable

- **GIVEN** `pdf-inspector` reports that OCR is required
- **AND** the isolated worker is absent, unprovisioned, incompatible, or unusable before dispatch
- **WHEN** the PDF is ingested
- **THEN** the system SHALL retain the available `pdf-inspector` Markdown rather than fabricate missing content
- **AND** the document/file result SHALL report that OCR was required but unavailable
- **AND** ingestion SHALL remain within the existing per-file degradation boundary

## ADDED Requirements

### Requirement: Page-level OCR routing SHALL OCR only pages that need it

When `OCR__ROUTING_UNIT=page` and OCR is enabled, the pdf-inspector path SHALL decide OCR need per page from a scan of every page. Pages that do not need OCR SHALL keep native pdf-inspector Markdown. Pages that need OCR SHALL be processed by the local OCR tier, unless a support pre-check rejects the page. The pre-check SHALL reject a page whose script or typography falls outside the local model's supported set, and a rejected page SHALL skip the local tier and escalate directly. A page SHALL escalate to the PaddleOCR-VL worker only when the pre-check rejects it, or the local tier returns no text, reports confidence below the configured minimum, or recommends hosted OCR. The worker SHALL receive only escalated pages. The emitted document SHALL join pages in page order and SHALL carry scalar counts of native, local-OCR, worker and unresolved pages. The default routing unit SHALL remain `document`.

#### Scenario: Only flagged pages are OCRed

- **GIVEN** the `page` routing unit and a 20-page PDF with 3 pages needing OCR
- **WHEN** the PDF is ingested
- **THEN** the 17 other pages SHALL keep native Markdown
- **AND** only the 3 flagged pages SHALL be processed by the local OCR tier

#### Scenario: Unsupported script skips the local tier

- **GIVEN** the `page` routing unit and a flagged page whose script is outside the local model's supported set
- **WHEN** the PDF is ingested
- **THEN** the local OCR tier SHALL NOT be run for that page
- **AND** that page SHALL be sent to the worker
- **AND** the metadata SHALL count it as a worker page

#### Scenario: Unreadable local OCR pages escalate alone

- **GIVEN** the local OCR tier returns no text for 1 of 3 flagged pages
- **AND** the isolated worker is available
- **WHEN** the PDF is ingested
- **THEN** exactly that page SHALL be sent to the worker
- **AND** the metadata SHALL count 1 worker page and 2 local-OCR pages

#### Scenario: Missing worker keeps local OCR text

- **GIVEN** a page escalates and the worker is unavailable
- **WHEN** the PDF is ingested
- **THEN** the page SHALL keep its local OCR text, or native text when local OCR produced none
- **AND** the page SHALL be counted as unresolved without failing the file

#### Scenario: Missing local OCR runtime degrades to native text

- **GIVEN** the `page` routing unit and no usable PDFium library or ONNX Runtime
- **WHEN** a PDF with flagged pages is ingested
- **THEN** flagged pages SHALL keep native text and be counted as unresolved
- **AND** a warning SHALL name the missing runtime once per operation

#### Scenario: Document unit is unchanged

- **GIVEN** no routing unit is configured
- **WHEN** a PDF is ingested
- **THEN** routing SHALL follow the whole-PDF behaviour of the `document` unit
