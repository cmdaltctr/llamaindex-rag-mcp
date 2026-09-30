# Spec Delta

Baseline note: this delta is rebased on the archived `page-level-ocr-routing` change (archived 2026-09-28). The routing requirement below matches the archived text except for the OCR-route wording, and the page-level routing requirement is modified so that escalated pages go to the OCR routes (task 0.1).

## MODIFIED Requirements

### Requirement: pdf-inspector SHALL route OCR-required PDFs to an isolated document-understanding worker

When the configured PDF path uses `pdf_inspector`, the system SHALL use the existing `pdf-inspector` result as both the fast extraction result and the evidence for deciding whether OCR/document understanding is required. Text-based PDFs with acceptable extraction quality SHALL keep the `pdf-inspector` Markdown. When an OCR route is available and OCR is enabled, scanned and image-based PDFs SHALL route unconditionally. Other types, including mixed PDFs, SHALL route only when a positive configured threshold condition is met, or when the maths-page condition is met. A confidence below the minimum or an OCR-page proportion at or above the configured fraction SHALL select OCR. A zero threshold SHALL disable its condition.

Every dispatch SHALL use the primary OCR route (dots.mocr by default), and the fallback route (PaddleOCR-VL by default) when the primary is unavailable before dispatch.

Layout complexity alone SHALL NOT require OCR. A text-based multi-column or table-heavy PDF that `pdf-inspector` extracts acceptably SHALL remain on the fast path, unless it has maths pages.

With the `document` routing unit (the default), the system SHALL route the whole PDF to the worker when the OCR condition is met and SHALL NOT merge page fragments from two PDF engines. With the `page` routing unit, routing SHALL follow the page-level OCR routing requirement instead.

#### Scenario: Clean text-based PDF stays on pdf-inspector without starting the parsing worker

- **GIVEN** `pdf_inspector` is the configured PDF path and the OCR worker is available
- **AND** `pdf-inspector` classifies the PDF as text-based with acceptable extraction quality and no material OCR requirement
- **AND** the PDF has no maths pages
- **WHEN** the PDF is ingested
- **THEN** the `pdf-inspector` Markdown SHALL be used
- **AND** no OCR parse request SHALL be dispatched
- **AND** the long-lived worker and its model SHALL NOT be started

#### Scenario: Complex text layout does not imply OCR

- **GIVEN** a text-based PDF containing multiple columns or tables and no maths pages
- **AND** `pdf-inspector` extracts the layout with acceptable quality
- **WHEN** the PDF is ingested
- **THEN** the PDF SHALL remain on the `pdf-inspector` path
- **AND** layout complexity alone SHALL NOT start or invoke the OCR worker

#### Scenario: Scanned or image-based PDF uses the OCR worker

- **GIVEN** `pdf-inspector` classifies a PDF as scanned or image-based
- **AND** the capability probe reports that the primary OCR route is available and compatible
- **WHEN** the PDF is ingested
- **THEN** the whole PDF SHALL be parsed by the primary OCR route
- **AND** the worker result SHALL replace the partial `pdf-inspector` extraction as the downstream document text

#### Scenario: Mixed PDF with material OCR requirement uses the worker

- **GIVEN** the `document` routing unit is configured
- **AND** `pdf-inspector` reports mixed content or material `pages_needing_ocr`
- **AND** the configured routing gate selects OCR
- **AND** the capability probe reports that the primary OCR route is available and compatible
- **WHEN** the PDF is ingested
- **THEN** the whole PDF SHALL be parsed by the primary OCR route
- **AND** the system SHALL NOT stitch independently parsed page fragments from the two engines

#### Scenario: Mixed PDF with zero thresholds stays on the fast path

- **GIVEN** OCR is enabled and a PDF is classified as mixed
- **AND** both routing thresholds are zero
- **AND** the PDF has no maths pages
- **WHEN** the PDF is ingested
- **THEN** no OCR parse request SHALL be dispatched
- **AND** the existing extracted Markdown and page diagnostics SHALL be preserved

#### Scenario: OCR required but the worker is unavailable

- **GIVEN** `pdf-inspector` reports that OCR is required
- **AND** both OCR routes are absent, unprovisioned, incompatible, or unusable before dispatch
- **WHEN** the PDF is ingested
- **THEN** the system SHALL retain the available `pdf-inspector` Markdown rather than fabricate missing content
- **AND** the document/file result SHALL report that OCR was required but unavailable
- **AND** ingestion SHALL remain within the existing per-file degradation boundary

### Requirement: The PaddleOCR-VL fallback SHALL run in an isolated worker environment

The fallback-route OCR engine SHALL be PaddleOCR-VL, and the primary-route engine SHALL be dots.mocr. PaddleOCR-VL SHALL use the supported PaddleOCR-VL document pipeline, including layout/region processing, reading-order handling, recognition, and result assembly. It SHALL NOT treat the VLM checkpoint as a bare whole-page string OCR call when the pipeline can preserve document structure.

Every OCR engine SHALL run as a local subprocess in a separate environment provisioned from its own engine-owned lockfile. Each engine project SHALL declare Python `>=3.11,<3.14` and SHALL own all of its model-runtime packages: PaddleOCR, PaddleX and PaddlePaddle for PaddleOCR-VL; PyTorch and transformers for dots.mocr; and any accelerator packages.

OMRG's main package metadata, root lockfile, and main runtime environment SHALL NOT include any engine's model-runtime packages. OMRG runtime modules SHALL NOT import them. The OMRG side SHALL communicate with every engine only through the subprocess protocol.

Every engine SHALL emit structured Markdown suitable for the same downstream Markdown chunking path used by `pdf-inspector` output.

#### Scenario: Worker result preserves structured document elements

- **GIVEN** an OCR-required PDF containing headings, paragraphs, and a table
- **WHEN** an isolated engine successfully parses the document
- **THEN** the emitted text SHALL be Markdown
- **AND** structural elements available from the parser SHALL be represented in that Markdown rather than flattened into an undifferentiated text stream

#### Scenario: Main OMRG environment remains Paddle-free

- **GIVEN** OMRG is installed from its main package metadata and root lockfile
- **WHEN** the package starts and processes content without any engine environment
- **THEN** no PaddleOCR, PaddleX, PaddlePaddle, PyTorch or transformers package SHALL be required or imported
- **AND** the server SHALL remain usable for every existing non-OCR path

#### Scenario: Worker is provisioned from its own lockfile

- **GIVEN** a Python interpreter in the supported `>=3.11,<3.14` range
- **WHEN** an OCR engine is provisioned
- **THEN** its environment SHALL be resolved from that engine's lockfile
- **AND** provisioning SHALL NOT add the engine's packages to OMRG's main environment

#### Scenario: Worker smoke test is independent of the main environment

- **GIVEN** an engine has been provisioned from its lockfile
- **WHEN** its standalone smoke test runs
- **THEN** the capability probe SHALL return a schema-valid manifest
- **AND** a small OCR fixture SHALL return schema-valid structured Markdown
- **AND** the test SHALL NOT require the engine's packages in OMRG's main environment

### Requirement: PDF extraction branches SHALL converge on one structured-Markdown contract

Successful `pdf-inspector` extraction and successful extraction by any OCR engine SHALL provide downstream ingestion with Markdown plus honest metadata. Existing source/provenance metadata SHALL be preserved. OCR-specific metadata SHALL be additive and SHALL NOT overwrite more authoritative existing values.

The change SHALL NOT require a new canonical document class or a second chunking pipeline.

#### Scenario: Fast and OCR paths enter the same Markdown chunking branch

- **GIVEN** one PDF succeeds through `pdf-inspector` and another succeeds through an OCR engine
- **WHEN** their reader results reach document chunking
- **THEN** both SHALL declare or otherwise carry Markdown as their emitted text format
- **AND** both SHALL be eligible for the same Markdown chunking strategy

#### Scenario: OCR diagnostics are honest

- **WHEN** a PDF result is emitted
- **THEN** metadata SHALL make it possible to distinguish whether OCR was required and whether OCR was actually used
- **AND** a result produced only by `pdf-inspector` SHALL NOT claim that an OCR engine processed the document
- **AND** a result produced by an OCR engine SHALL name that engine

### Requirement: Source index identity SHALL include the resolved OCR worker fingerprint

The existing source index identity SHALL include the OCR routing configuration, the sorted unconditional routing type set, and a deterministic worker fingerprint for each OCR route: primary and fallback. Each fingerprint SHALL include worker availability, protocol version, package names and exact versions, pipeline identity and revision, model identity and revision, and output-schema identity and version. It SHALL exclude transient process details such as process identifiers. An unavailable or unconfigured route SHALL contribute a stable unavailable fingerprint rather than an omitted field.

The fingerprints SHALL be recorded for every source through the existing index-identity mechanism. A change to any fingerprint field SHALL invalidate the prior identity so byte-identical sources are re-ingested. The initial payload extension used schema 4. The routing-policy amendment used schema 5 so existing identities cannot silently omit the unconditional routing set. The two-route amendment SHALL advance the schema by one from the schema current when it lands.

#### Scenario: Provisioning an unavailable worker triggers re-ingestion

- **GIVEN** a source was indexed while a route's fingerprint recorded unavailable
- **WHEN** that route's engine is provisioned and its capability probe succeeds
- **THEN** the source index identity SHALL change
- **AND** a byte-identical source SHALL be re-ingested rather than reported `skipped_unchanged`

#### Scenario: Worker contract or model change triggers re-ingestion

- **GIVEN** a source was indexed with one resolved fingerprint per route
- **WHEN** the protocol version, package versions, pipeline identity, model identity, or output-schema identity of either route changes
- **THEN** the source index identity SHALL change
- **AND** a byte-identical source SHALL be re-ingested rather than reported `skipped_unchanged`

#### Scenario: Unchanged worker fingerprint preserves unchanged-source behaviour

- **GIVEN** the source bytes, OCR routing configuration, and resolved fingerprints of both routes are unchanged
- **WHEN** the source is ingested again
- **THEN** the worker fingerprints SHALL NOT alone prevent the existing `skipped_unchanged` result

### Requirement: Page-level OCR routing SHALL OCR only pages that need it

When `OCR_ROUTING_UNIT=page` and OCR is enabled, the pdf-inspector path SHALL decide OCR need per page from a scan of every page. Pages that do not need OCR SHALL keep native pdf-inspector Markdown. Pages that need OCR SHALL be processed by the local OCR tier. A page SHALL escalate to the OCR routes only when the local tier returns no text or only whitespace, reports no confidence or a confidence below the configured minimum, or recommends hosted OCR. Escalated pages SHALL go in one page-listed request to the primary OCR route, or to the fallback route when the primary is unavailable before dispatch. The OCR routes SHALL receive only escalated pages. The emitted document SHALL join pages in page order and SHALL carry scalar counts of native, local-OCR, worker and unresolved pages, which SHALL sum to the page count. The default routing unit SHALL remain `document`.

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
- **AND** an OCR route is available
- **AND** the worker returns usable, non-empty Markdown for the escalated page
- **WHEN** the PDF is ingested
- **THEN** exactly that page SHALL be sent to the worker
- **AND** the metadata SHALL count 1 worker page and 2 local-OCR pages

#### Scenario: Missing worker keeps local OCR text

- **GIVEN** a page escalates and both OCR routes are unavailable
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
