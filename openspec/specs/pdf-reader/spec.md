## Purpose

Define a pluggable PDF reader architecture with environment-variable-driven backend selection, bounding-box metadata capture, graceful fallback across multiple parser backends, and structured error handling for MCP tool compliance.

## Requirements

### Requirement: PDF reader SHALL be selectable via environment variable

The system SHALL read a `PDF_READER` environment variable at config-load
time into the frozen `Settings.pdf_reader` field. Accepted values SHALL be
`auto`, `pdf_inspector`, `liteparse`, `pypdfium2`, and `pypdf`. Any other
value SHALL log a warning naming the offending value and fall back to
`auto`. The composition root SHALL resolve `auto` to a concrete backend
name exactly once at startup and bake the result into the injected
`EffectiveSettings.pdf_reader`; no module-level resolved constant exists.

#### Scenario: Explicit pdf-inspector selection via env var

- **WHEN** `PDF_READER=pdf_inspector` is set and the package is importable
- **THEN** the injected `EffectiveSettings.pdf_reader` SHALL equal `"pdf_inspector"` and its adapter SHALL ingest all `.pdf` files

#### Scenario: Explicit override selection via env var

- **WHEN** `PDF_READER=liteparse` is set and the `liteparse` package is importable
- **THEN** the injected `EffectiveSettings.pdf_reader` SHALL equal `"liteparse"` and the LiteParse adapter SHALL be used for all `.pdf` ingestion

#### Scenario: Unknown value falls back to auto with warning

- **WHEN** `PDF_READER=fastparser` (an unsupported value) is set
- **THEN** the system SHALL log a warning naming the offending value and the fallback, and SHALL resolve as if `PDF_READER=auto` had been set

#### Scenario: Resolution happens once at the composition root

- **WHEN** the server or CLI entry point starts
- **THEN** `compose.resolve_pdf_reader` SHALL run once over the frozen settings
- **AND** every operation below the entry point SHALL read the concrete name from its injected settings, with no repeated probing

### Requirement: Auto resolution SHALL probe backends in preference order with graceful fallback

When the configured reader is `auto`, the system SHALL probe backend imports
in the order `liteparse → pypdfium2 → pypdf` and SHALL select the first
importable backend. PyMuPDF is structurally excluded from accepted values
entirely (AGPL-3 incompatibility). If no optional backend is installed, the
system SHALL fall back to `pypdf` (always available via
`llama-index-readers-file`).

The composition root resolves `auto` once at startup and injects the concrete
name. Callers that bypass the composition root (direct library use, tests)
SHALL receive the same preference order from the reader factory's local
resolution, so the selected backend is identical on both paths for the same
installed packages.

#### Scenario: LiteParse installed and selected by auto

- **WHEN** the configured reader is `auto` and the `liteparse` package is importable
- **THEN** the resolved reader SHALL be `liteparse`

#### Scenario: LiteParse missing, pypdfium2 installed

- **WHEN** the configured reader is `auto`, `liteparse` is not importable, and `pypdfium2` is importable
- **THEN** the resolved reader SHALL be `pypdfium2` and the system SHALL log an informational message that LiteParse was not available

#### Scenario: No optional backend installed

- **WHEN** the configured reader is `auto` and neither `liteparse` nor `pypdfium2` is importable
- **THEN** the resolved reader SHALL be `pypdf` and ingestion SHALL behave identically to the pre-change pipeline

#### Scenario: Explicit backend requested but not installed

- **WHEN** the configured reader is `liteparse` but `liteparse` is not importable
- **THEN** the system SHALL log an error naming the missing package and SHALL fall back to `pypdf` rather than raising

#### Scenario: Factory-local auto resolution matches composition-root order

- **WHEN** the reader factory resolves `auto` for a caller that bypassed the composition root, `liteparse` is not importable, and `pypdfium2` is importable
- **THEN** the factory SHALL return the `pypdfium2` adapter
- **AND** the selection SHALL match what the composition root would have resolved for the same installed packages

### Requirement: Reader failures SHALL surface as MCP error dictionaries, never exceptions

The ingestion pipeline SHALL catch every per-file reader failure (corrupt
PDF, native failure surfaced as a Python exception, IO failure, encoding
error) around the chunking stage
and convert it into a structured file detail through
`core/ingestion/loader.py:make_file_detail`:
`{"file": "<filename>", "status": "failed", "chunks": 0, "error":
"<human-readable detail>"}`. Reader adapters themselves SHALL NOT be
required to catch their parser's exceptions. No exception SHALL propagate
out of `ingest_path_async` or any MCP tool handler, per the project's
"Never raise from MCP tool handlers" gotcha (AGENTS.md).

#### Scenario: Corrupt PDF raises inside adapter

- **WHEN** a `.pdf` file is structurally corrupt and the underlying parser raises an exception
- **THEN** the ingestion pipeline SHALL catch the exception, log it with the filename, and append a structured error detail with `status="failed"` and a descriptive message
- **AND** the exception SHALL NOT propagate to the `ingest_documents` caller

#### Scenario: LiteParse native crash

- **WHEN** the LiteParse native library crashes (segfault wrapper, FFI panic, or Rust panic propagated through `pyo3`)
- **THEN** the ingestion pipeline SHALL catch the resulting Python-visible exception, log it, and append a structured error detail
- **AND** ingestion of subsequent files in the same batch SHALL continue uninterrupted

#### Scenario: Error contract matches make_file_detail shape

- **WHEN** the ingestion pipeline converts any reader failure into a file detail
- **THEN** the dictionary SHALL contain exactly the keys `file` (str), `status` (literal `"failed"`), `chunks` (int `0`), and `error` (str with human-readable detail)
- **AND** the dictionary SHALL be appendable to the `file_details` list in `ingest_path_async` without further transformation

### Requirement: LiteParse adapter SHALL capture bounding-box metadata on emitted Documents

When the LiteParse adapter is in use, every emitted `Document` object SHALL carry a `metadata` dictionary containing spatial information extracted by LiteParse. The metadata SHALL include the keys `pdf_reader="liteparse"`, `page=<int>` (1-indexed), `column=<"left"|"right"|"single"|"multi_column">`, `section_bbox=<[x0, y0, x1, y1]>` (page-coordinate space), and `bbox_schema_version=1`. A page the adapter joins column by column SHALL carry `column="multi_column"`, so the label names the order the text is in. Retrieval-side consumption of these fields is out of scope for this change.

#### Scenario: Two-column academic PDF
- **WHEN** a two-column academic PDF is ingested via the LiteParse adapter
- **THEN** each emitted Document for a page joined column by column SHALL have `metadata["column"]` set to `"multi_column"`
- **AND** a two-column page the classifier does not recognise SHALL keep `"left"` or `"right"`
- **AND** `metadata["page"]` SHALL reflect the 1-indexed source page number

#### Scenario: Single-column PDF
- **WHEN** a single-column PDF is ingested via the LiteParse adapter
- **THEN** each emitted Document SHALL have `metadata["column"]` set to `"single"`

#### Scenario: Non-LiteParse readers do not emit bbox fields
- **WHEN** a PDF is ingested via the pypdf or pypdfium2 adapter
- **THEN** emitted Documents SHALL NOT carry `section_bbox`, `column`, or `bbox_schema_version` keys (these are LiteParse-specific)
- **AND** `metadata["pdf_reader"]` SHALL be set to the backend name (`"pypdf"` or `"pypdfium2"`) for diagnostics

### Requirement: Reader factory SHALL be extensible without modifying ingestion code

New reader adapters SHALL be addable by creating a single module in
`src/omrg/integrations/pdf/` and registering it with one
`registry.register()` call. The shared contract is the duck-typed
`load_data(file) -> list[Document]` method — there is no separate protocol
module. The ingestion call sites SHALL NOT require modification when a new
reader is added; only the accepted values in `config/` and the registry
registration SHALL change. The factory receives the reader name from its
caller: `get_pdf_reader(reader)`.

#### Scenario: Adding a new adapter

- **WHEN** a developer creates `src/omrg/integrations/pdf/spdf.py` with a `load_data` method and adds `"spdf"` to the accepted values in `config/` plus one `register("spdf", "...")` call in the registry
- **THEN** no other source file SHALL require modification to make `PDF_READER=spdf` functional

#### Scenario: Factory returns adapter, not reader instance

- **WHEN** `get_pdf_reader(reader)` is called with a concrete reader name
- **THEN** it SHALL return an adapter instance with a `load_data` method, not a parsed-document instance, so `SimpleDirectoryReader(file_extractor={".pdf": get_pdf_reader(resolved.pdf_reader)})` works at the ingestion call site

#### Scenario: Factory dispatch behaviour unchanged

- **WHEN** the `auto` backend resolution runs after the relocation
- **THEN** backend preference order, graceful fallback, and `PDF_READER` env var handling SHALL be identical to the pre-refactor factory (ADR-020 amended for location only)

### Requirement: LiteParse SHALL be a core dependency

Both `liteparse` and `pdf-inspector` SHALL be declared in the main
`[project.dependencies]` list in `pyproject.toml`, not as optional extras.
The base `uv sync` SHALL install both packages and make the configured
default available without an optional dependency extra. The `auto`
resolution order SHALL prefer LiteParse when importable.

#### Scenario: Baseline install includes pdf-inspector
- **WHEN** a user runs `uv sync` without any extras
- **THEN** `pdf_inspector` and `liteparse` SHALL be importable

#### Scenario: Explicit override to LiteParse
- **WHEN** a user sets `PDF_READER=liteparse` in `.env`
- **THEN** the system SHALL use LiteParse regardless of pdf-inspector availability

### Requirement: PDF reader default SHALL be configuration-owned after Experiment 14 validation

The packaged `PDF_READER` default SHALL be `pdf_inspector`. The selected
backend SHALL remain configurable through `PDF_READER`; `auto` SHALL retain
its existing capability-resolution and graceful-fallback behaviour. Experiment
14 validated this promotion with zero parser failures, a 346.7-second ingest
run, and the highest reranked Hit@5 result (0.6250).

#### Scenario: Packaged default selects pdf-inspector

- **WHEN** no `PDF_READER` environment variable is set
- **THEN** the resolved reader SHALL be `"pdf_inspector"`

#### Scenario: Environment override takes precedence

- **WHEN** `PDF_READER=pypdf` is set
- **THEN** the system SHALL use pypdf regardless of the packaged default

#### Scenario: Missing configured backend falls back safely

- **WHEN** `PDF_READER=pdf_inspector` is configured but the package is not importable
- **THEN** the system SHALL log an error naming the missing package and fall back to pypdf rather than raising

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

### Requirement: The OCR worker SHALL use a versioned JSON Lines protocol

OMRG SHALL send UTF-8 requests as one complete JSON object per line on the worker's standard input. The worker SHALL return one complete JSON object per line on standard output. Every request and response SHALL include a request identifier and protocol version. Every accepted parse request SHALL receive one terminal success or error response with the same request identifier while the worker remains healthy.

Standard output SHALL contain protocol messages only. Worker diagnostics and operational logs SHALL use standard error so they cannot corrupt protocol framing. OMRG SHALL drain standard error independently from standard output.

The capability probe SHALL report worker availability, protocol version, relevant package names and exact versions, pipeline identity and revision, model identity and revision, and output-schema identity and version. It SHALL use metadata and static worker declarations without initialising Paddle, importing model code, loading model weights, or leaving the long-lived parsing worker running. Missing files, an unusable environment, malformed probe output, or an incompatible protocol SHALL produce a stable unavailable fingerprint before parse dispatch.

A successful parse response SHALL contain structured Markdown and metadata that conform to the reported output schema.

#### Scenario: Capability probe returns the worker fingerprint without loading the model

- **GIVEN** the isolated worker environment is provisioned
- **WHEN** OMRG performs the capability probe
- **THEN** the probe SHALL report availability and every required worker identity field
- **AND** it SHALL NOT initialise Paddle or import model code
- **AND** it SHALL NOT leave a long-lived parsing worker running

#### Scenario: Parse request and response remain correlated

- **GIVEN** the routing gate selects OCR and the worker capability is compatible
- **WHEN** OMRG writes a parse request line to the worker
- **THEN** the worker SHALL return one terminal JSON response line with the same request identifier
- **AND** the response SHALL declare the negotiated protocol and output-schema identities

#### Scenario: Worker logging does not contaminate protocol output

- **GIVEN** the worker emits a diagnostic while handling a request
- **WHEN** OMRG reads the worker streams
- **THEN** the diagnostic SHALL be read from standard error
- **AND** standard output SHALL remain parseable as JSON Lines protocol messages only

#### Scenario: Incompatible worker is unavailable before dispatch

- **GIVEN** the capability probe reports an unsupported protocol or output-schema identity
- **WHEN** an OCR-required PDF reaches the routing seam
- **THEN** OMRG SHALL NOT dispatch the PDF to that worker
- **AND** the unavailable-worker degradation behaviour SHALL apply

### Requirement: The OCR parsing worker SHALL be lazy and long-lived

The long-lived parsing subprocess and its model SHALL start only when the first OCR parse request is dispatched. A healthy subprocess SHALL be reused for later OCR requests owned by the same engine. The client SHALL permit one request in flight at a time. The owning engine SHALL close the subprocess during orderly shutdown.

A timed-out, crashed, or protocol-invalid subprocess SHALL be discarded. The failed request SHALL NOT be replayed automatically. A later OCR request SHALL start a fresh subprocess when the capability remains available, but the failed file SHALL retain its structured per-file error result.

#### Scenario: First OCR dispatch starts the worker

- **GIVEN** the capability probe reports an available worker
- **AND** no OCR parse request has yet been dispatched
- **WHEN** the routing seam dispatches the first OCR-required PDF
- **THEN** the long-lived parsing subprocess SHALL start
- **AND** the OCR model SHALL initialise within that subprocess

#### Scenario: Healthy worker is reused

- **GIVEN** a healthy parsing worker has completed one OCR request
- **WHEN** another OCR-required PDF is dispatched by the same owner
- **THEN** the existing subprocess SHALL handle the request
- **AND** the model SHALL NOT be initialised in a second subprocess

#### Scenario: Owner shutdown closes the worker

- **GIVEN** the owner has a running parsing worker
- **WHEN** the owner shuts down normally
- **THEN** it SHALL close the worker's input and terminate the subprocess within a bounded period

#### Scenario: Later request replaces a failed worker

- **GIVEN** a parsing worker timed out or crashed during an earlier request
- **WHEN** a later OCR-required PDF is dispatched
- **THEN** the failed subprocess SHALL NOT be reused
- **AND** a fresh subprocess SHALL be started for the later request

### Requirement: Post-dispatch worker failure SHALL be a structured per-file error

Parse dispatch occurs when OMRG has written and flushed the complete JSON Lines request. If the worker times out, crashes, closes its output, violates the protocol, or returns a structured error after that point, OMRG SHALL return a structured error for that file. It SHALL NOT report the partial `pdf-inspector` result as a successful or degraded extraction for the failed attempt.

The failed source version SHALL NOT be marked current. The existing failure-safe replacement boundary SHALL preserve any prior current version. Other files in the same ingestion batch SHALL continue within the existing per-file error boundary.

#### Scenario: Worker times out after parse dispatch

- **GIVEN** OMRG has written and flushed a complete parse request
- **WHEN** the worker does not return a terminal response within the configured timeout
- **THEN** that file SHALL receive a structured timeout error
- **AND** its source version SHALL NOT be marked current
- **AND** subsequent files in the batch SHALL continue

#### Scenario: Worker crashes after parse dispatch

- **GIVEN** OMRG has written and flushed a complete parse request
- **WHEN** the worker exits before returning the terminal response
- **THEN** that file SHALL receive a structured worker-crash error
- **AND** its source version SHALL NOT be marked current
- **AND** any prior current source version SHALL be preserved
- **AND** subsequent files in the batch SHALL continue

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

### Requirement: The OCR routing gate SHALL be calibrated evidence expressed as injected configuration

The threshold that selects the OCR fallback SHALL be a calibrated value carried in injected configuration, not a constant in the routing module. It SHALL follow the shape the existing PDF knobs already use: top-level fields on the effective settings beside `pdf_reader` and `liteparse_ocr_enabled`, resolved once at the composition root and passed downstream.

The gate SHALL be calibrated on a committed fixture set disjoint from the fixtures used to evaluate whether the OCR fallback improves retrieval. Calibration SHALL report routing behaviour — text-based PDFs the gate would route to OCR, and OCR-required PDFs it would leave on the fast path — and SHALL NOT be the same run that measures downstream retrieval quality.

The packaged default SHALL be the promoted pair validated by the repeat routing study
(`29-pdf-routing-repeat-2026-09-13`): routing enabled, `0.5` minimum
confidence, `0.10` flagged-page fraction. The enable flag and both
thresholds SHALL ship together — enabling routing while leaving
thresholds at the `0.0` sentinels is the bare-enable configuration the
study showed silently misses threshold-flagged documents, and packaged
defaults SHALL NOT present it. `config/` SHALL NOT probe the worker, and no module SHALL read a settings singleton to obtain the gate.

#### Scenario: Routing threshold is read from injected settings

- **WHEN** the routing seam decides whether a PDF needs OCR
- **THEN** it SHALL read the gate from the injected effective settings
- **AND** the routing module SHALL NOT contain a hardcoded threshold constant

#### Scenario: Calibration and evaluation fixtures are disjoint

- **GIVEN** the committed PDF calibration fixtures and the committed PDF evaluation fixtures
- **WHEN** the OCR routing gate is calibrated
- **THEN** calibration SHALL use only the calibration fixtures
- **AND** the evaluation fixtures SHALL remain unused until the Stage 5 ablation

#### Scenario: Packaged default routes OCR-required PDFs

- **GIVEN** a fresh installation whose operator has set no OCR routing configuration
- **AND** the isolated OCR worker is provisioned and compatible
- **WHEN** a scanned PDF is ingested
- **THEN** the OCR fallback SHALL be selected
- **AND** a healthy text-based PDF SHALL stay on the fast path

#### Scenario: Unprovisioned worker degrades deterministically

- **GIVEN** a fresh installation with no OCR worker provisioned
- **WHEN** an OCR-required PDF is ingested
- **THEN** the file SHALL keep the partial pdf-inspector extraction with degraded diagnostics
- **AND** the batch SHALL continue with an actionable warning naming the provisioning step

### Requirement: pdf-inspector silent-empty extraction SHALL recover via a plain-text retry

When the pdf-inspector reader classifies a PDF as `text_based` while its own Markdown extraction is empty and the page count is greater than zero, the adapter SHALL retry the file with the registered `liteparse` reader in extraction-only mode (OCR disabled regardless of operator settings), joining the per-page text into one document for the whole file, so a readable text layer is not silently discarded. The rescue tier SHALL receive concrete OCR and worker settings so it does not require default effective settings. When liteparse is unavailable or its retry yields no text, the adapter SHALL retry with the registered `pypdf` reader, preserving the same one-document contract.

A successful retry SHALL correct the routing evidence it emits: the scalar `pages_needing_ocr` SHALL be set to zero, because the pages were flagged only by the failed extraction, and the pre-fallback flagged count SHALL be preserved under an additive diagnostic key. A retry chain that yields no text from either tier SHALL leave the original pdf-inspector result unchanged so the OCR routing gate still sees the flagged evidence. Diagnostics SHALL be additive, and `extraction_fallback_backend` SHALL name the tier that produced the text (`liteparse` or `pypdf`); diagnostics SHALL NOT claim the OCR worker or any other backend produced it.

#### Scenario: Contradiction triggers the retry

- **GIVEN** pdf-inspector returns `pdf_type=text_based`, non-zero `page_count`, and empty Markdown
- **WHEN** the adapter emits its document
- **THEN** the document text SHALL be the joined liteparse per-page extraction
- **AND** the document SHALL carry an additive diagnostic naming liteparse as the fallback backend

#### Scenario: Bare direct adapter use stays on liteparse

- **GIVEN** no default effective settings were installed
- **WHEN** the contradiction triggers and liteparse can recover text
- **THEN** the liteparse tier SHALL run with OCR disabled and automatic worker selection
- **AND** pypdf SHALL NOT be selected

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

### Requirement: LiteParse adapter SHALL emit multi-column pages in reading order

The LiteParse adapter SHALL classify each page's layout from its own text items before joining them into text. A page classified `multi_column` SHALL be joined column by column: every item of the first column in vertical order, then every item of the next column. A page not classified `multi_column` SHALL keep the order the library returned, so single-column pages, tables and layouts the classifier does not recognise are unchanged, and SHALL keep the `column` label the adapter emits today.

Classification SHALL depend only on the geometry of the page's own text items and SHALL NOT read the document, the file name or any setting. It SHALL require a vertical gutter: a band of the page's horizontal extent that the page's own non-full-width items leave essentially uncovered, whose centre lies in the middle third of that extent, with text on both sides of comparable quantity, each side spanning most of the page's vertical text extent. A page that fails any of those conditions SHALL keep the library order and SHALL NOT be labelled `multi_column`.

Reordering SHALL NOT add, drop or alter any item. Together with the line join below, the only change to a page's characters SHALL be whitespace.

#### Scenario: Two-column body page is emitted column by column

- **GIVEN** a page whose text items form two columns separated by a gutter
- **WHEN** the adapter emits its Document
- **THEN** the text SHALL contain every item of the left column, in vertical order, before any item of the right column

#### Scenario: Single-column page keeps the library order

- **GIVEN** a page whose items leave no qualifying gutter
- **WHEN** the adapter emits its Document
- **THEN** the text SHALL be the items joined in the order LiteParse returned them

#### Scenario: A table is not reordered

- **GIVEN** a page whose items are laid out in rows across the page with no qualifying gutter
- **WHEN** the adapter emits its Document
- **THEN** the item order SHALL be unchanged
- **AND** the page SHALL NOT be labelled `multi_column`

#### Scenario: Reordering preserves content

- **GIVEN** any page the adapter reorders
- **WHEN** the adapter emits its Document
- **THEN** the multiset of item texts in the output SHALL equal the multiset LiteParse returned

### Requirement: LiteParse adapter SHALL join the items of one visual line

The adapter SHALL join consecutive items that sit on one visual line, left to right, into one line of text. Two items share a line when their vertical ranges overlap by at least half the shorter item's height and the second starts at or to the right of the first. Items on one line SHALL be joined by a single space, or by no space when the horizontal gap is under one tenth of the shorter height (a kerning split). A gap wider than the taller item's height SHALL start a new line, so a sidebar and the body beside it are never joined. Every other item boundary SHALL be a line break. The join SHALL NOT change item order or item text.

#### Scenario: Words drawn separately form one line

- **GIVEN** a title whose words are separate items at the same height
- **WHEN** the adapter emits its Document
- **THEN** the title SHALL be one line, its words separated by single spaces

#### Scenario: A column gap breaks the line

- **GIVEN** two items at the same height separated by more than one text height
- **WHEN** the adapter emits its Document
- **THEN** they SHALL be on separate lines

#### Scenario: A kerning split rejoins without a space

- **GIVEN** two pieces of one word with no gap between them
- **WHEN** the adapter emits its Document
- **THEN** they SHALL be joined with no space

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

### Requirement: Local OCR tier SHALL escalate pages below a default confidence of 0.9

When `OCR_ROUTING_UNIT=page` and the operator has not set `OCR_LOCAL_MIN_CONFIDENCE`, a page the local OCR tier reads SHALL escalate to the worker when its reported confidence is below 0.9. The tier SHALL keep a page whose confidence is 0.9 or higher, unless the page is empty, has no reported confidence, or carries the engine's hosted recommendation. A value the operator sets SHALL replace the default without change to the rule.

The page-unit index identity SHALL change when the effective cut changes, so that sources read under a different cut are re-indexed. The default `document` routing unit has no local tier, and its index identity SHALL NOT change.

#### Scenario: Page below the default cut escalates

- **GIVEN** `page` routing unit and no operator value for `OCR_LOCAL_MIN_CONFIDENCE`
- **WHEN** the local tier reads a page with text and confidence 0.85
- **THEN** the page SHALL escalate to the worker

#### Scenario: Page at the default cut stays local

- **GIVEN** `page` routing unit and no operator value for `OCR_LOCAL_MIN_CONFIDENCE`
- **WHEN** the local tier reads a page with text, confidence 0.9 and no hosted recommendation
- **THEN** the page SHALL keep its local text

#### Scenario: Operator value replaces the default

- **GIVEN** `OCR_LOCAL_MIN_CONFIDENCE=0.7`
- **WHEN** the local tier reads a page with text and confidence 0.75
- **THEN** the page SHALL keep its local text

#### Scenario: Page unit re-indexes when the default changes

- **GIVEN** a source indexed under `page` routing with the previous default cut of 0.8
- **WHEN** the source is ingested again under the default cut of 0.9
- **THEN** the source SHALL be re-indexed

#### Scenario: Document unit keeps its index identity

- **GIVEN** the default `document` routing unit
- **WHEN** the default cut changes from 0.8 to 0.9
- **THEN** the index identity of every source SHALL stay the same
