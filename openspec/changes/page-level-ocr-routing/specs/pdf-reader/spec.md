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

### Requirement: Unit-scoped metadata keys SHALL enter the index identity only under their unit

A metadata key that only one routing unit can emit SHALL contribute to `embedding_text.excluded_keys` in the source index identity only when that unit is active. The page-source counts are such keys: the `document` unit never puts them on a Document, so their presence in the centrally owned exclusion set cannot change a `document`-unit install's embedded text, and including them in its identity would reprocess every existing corpus for a key it can never emit.

This mirrors the routing unit's own treatment, which enters the identity only when it is not `document`. The keys SHALL remain in the one centrally owned exclusion set; a second list held by the PDF reader would exclude them from embedding text while moving no identity at all, on any unit.

#### Scenario: A document-unit install keeps the identity it had

- **GIVEN** the `document` routing unit and a source indexed before page routing existed
- **WHEN** its index identity is computed
- **THEN** the identity SHALL equal the identity computed before the page-source counts joined the exclusion set
- **AND** the source SHALL NOT be reprocessed

#### Scenario: A page-unit install includes them

- **GIVEN** the `page` routing unit
- **WHEN** its index identity is computed
- **THEN** the page-source counts SHALL contribute to `embedding_text.excluded_keys`

#### Scenario: Subtracted keys are never emitted on the document path

- **GIVEN** the `document` routing unit
- **WHEN** a PDF is ingested
- **THEN** the emitted metadata SHALL carry none of the page-source counts

### Requirement: Page-level OCR routing SHALL OCR only pages that need it

When `OCR_ROUTING_UNIT=page` and OCR is enabled, the pdf-inspector path SHALL decide OCR need per page from a scan of every page. Pages that do not need OCR SHALL keep native pdf-inspector Markdown. Pages that need OCR SHALL be processed by the local OCR tier. A page SHALL escalate to the PaddleOCR-VL worker only when the local tier returns no text or only whitespace, reports confidence below the configured minimum, or recommends hosted OCR. The worker SHALL receive only escalated pages. The emitted document SHALL join pages in page order and SHALL carry scalar counts of native, local-OCR, worker and unresolved pages, which SHALL sum to the page count. The default routing unit SHALL remain `document`.

The four existing OCR diagnostics SHALL remain scalars and SHALL keep their document-unit meaning. `ocr_required` SHALL be true when at least one page was flagged. `ocr_used` SHALL be true when OCR produced the text of at least one page, by either tier. `pages_needing_ocr` SHALL remain the count of flagged pages. `ocr_backend` SHALL name the one backend that produced all of the document's text, and SHALL be `mixed` when more than one produced text, so that it never names a backend that produced only part of a document.

#### Scenario: Page-source counts sum to the page count

- **GIVEN** the `page` routing unit and any ingested PDF
- **WHEN** the adapter emits its document
- **THEN** the native, local-OCR, worker and unresolved page counts SHALL sum to `page_count`

#### Scenario: A document read by two backends reports mixed

- **GIVEN** the `page` routing unit and a PDF whose text comes partly from native extraction and partly from OCR
- **WHEN** the adapter emits its document
- **THEN** `ocr_backend` SHALL be `mixed`
- **AND** it SHALL NOT name either contributing backend alone

#### Scenario: The document unit emits no page-source counts

- **GIVEN** no routing unit is configured
- **WHEN** a PDF is ingested
- **THEN** the emitted metadata SHALL NOT carry the native, local-OCR, worker or unresolved page counts

#### Scenario: Only flagged pages are OCRed

- **GIVEN** the `page` routing unit and a 20-page PDF with 3 pages needing OCR
- **WHEN** the PDF is ingested
- **THEN** the 17 other pages SHALL keep native Markdown
- **AND** only the 3 flagged pages SHALL be processed by the local OCR tier

#### Scenario: A page the local tier cannot read escalates

- **GIVEN** the `page` routing unit and a flagged page the local tier returns no text for
- **AND** the worker returns usable, non-empty Markdown for that page
- **WHEN** the PDF is ingested
- **THEN** that page SHALL be sent to the worker
- **AND** the metadata SHALL count it as a worker page

#### Scenario: Unreadable local OCR pages escalate alone

- **GIVEN** the local OCR tier returns no text for 1 of 3 flagged pages
- **AND** the isolated worker is available
- **AND** the worker returns usable, non-empty Markdown for the escalated page
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
