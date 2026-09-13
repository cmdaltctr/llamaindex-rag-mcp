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

When the LiteParse adapter is in use, every emitted `Document` object SHALL carry a `metadata` dictionary containing spatial information extracted by LiteParse. The metadata SHALL include the keys `pdf_reader="liteparse"`, `page=<int>` (1-indexed), `column=<"left"|"right"|"single">`, `section_bbox=<[x0, y0, x1, y1]>` (page-coordinate space), and `bbox_schema_version=1`. Retrieval-side consumption of these fields is out of scope for this change.

#### Scenario: Two-column academic PDF
- **WHEN** a two-column academic PDF is ingested via the LiteParse adapter
- **THEN** each emitted Document SHALL have `metadata["column"]` set to `"left"` or `"right"` reflecting the source column
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

When the configured PDF path uses `pdf_inspector`, the system SHALL use the existing `pdf-inspector` result as both the fast extraction result and the evidence for deciding whether OCR/document understanding is required. Text-based PDFs with acceptable extraction quality SHALL keep the `pdf-inspector` Markdown. When the isolated worker capability is available and OCR is enabled, scanned and image-based PDFs SHALL route unconditionally. Other types, including mixed PDFs, SHALL route only when a positive configured threshold condition is met. A confidence below the minimum or an OCR-page proportion at or above the configured fraction SHALL select OCR. A zero threshold SHALL disable its condition.

Layout complexity alone SHALL NOT require OCR. A text-based multi-column or table-heavy PDF that `pdf-inspector` extracts acceptably SHALL remain on the fast path.

The first implementation SHALL route the whole PDF to the worker when the OCR condition is met. It SHALL NOT merge page fragments from two PDF engines.

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

- **GIVEN** `pdf-inspector` reports mixed content or material `pages_needing_ocr`
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

### Requirement: The PaddleOCR-VL fallback SHALL run in an isolated worker environment

The OCR fallback SHALL use the supported PaddleOCR-VL document pipeline, including layout/region processing, reading-order handling, recognition, and result assembly. It SHALL NOT treat the VLM checkpoint as a bare whole-page string OCR call when the pipeline can preserve document structure.

The worker SHALL run as a local subprocess in a separate environment provisioned from a worker-owned lockfile. The worker project SHALL declare Python `>=3.11,<3.14` and SHALL own all PaddleOCR, PaddleX, PaddlePaddle, model-runtime, and accelerator packages.

OMRG's main package metadata, root lockfile, and main runtime environment SHALL NOT include those Paddle packages. OMRG runtime modules SHALL NOT import Paddle packages. The OMRG side SHALL communicate with the worker only through the subprocess protocol.

The worker SHALL emit structured Markdown suitable for the same downstream Markdown chunking path used by `pdf-inspector` output.

#### Scenario: Worker result preserves structured document elements

- **GIVEN** an OCR-required PDF containing headings, paragraphs, and a table
- **WHEN** the isolated worker successfully parses the document
- **THEN** the emitted text SHALL be Markdown
- **AND** structural elements available from the parser SHALL be represented in that Markdown rather than flattened into an undifferentiated text stream

#### Scenario: Main OMRG environment remains Paddle-free

- **GIVEN** OMRG is installed from its main package metadata and root lockfile
- **WHEN** the package starts and processes content without the isolated worker environment
- **THEN** no PaddleOCR, PaddleX, or PaddlePaddle package SHALL be required or imported
- **AND** the server SHALL remain usable for every existing non-OCR path

#### Scenario: Worker is provisioned from its own lockfile

- **GIVEN** a Python interpreter in the supported `>=3.11,<3.14` range
- **WHEN** the OCR worker is provisioned
- **THEN** its environment SHALL be resolved from the worker-owned lockfile
- **AND** provisioning SHALL NOT add Paddle packages to OMRG's main environment

#### Scenario: Worker smoke test is independent of the main environment

- **GIVEN** the isolated worker has been provisioned from its lockfile
- **WHEN** its standalone smoke test runs
- **THEN** the capability probe SHALL return a schema-valid manifest
- **AND** a small OCR fixture SHALL return schema-valid structured Markdown
- **AND** the test SHALL NOT require Paddle packages in OMRG's main environment

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

Both successful `pdf-inspector` extraction and successful PaddleOCR-VL worker extraction SHALL provide downstream ingestion with Markdown plus honest metadata. Existing source/provenance metadata SHALL be preserved. OCR-specific metadata SHALL be additive and SHALL NOT overwrite more authoritative existing values.

The change SHALL NOT require a new canonical document class or a second chunking pipeline.

#### Scenario: Fast and OCR paths enter the same Markdown chunking branch

- **GIVEN** one PDF succeeds through `pdf-inspector` and another succeeds through the OCR worker
- **WHEN** their reader results reach document chunking
- **THEN** both SHALL declare or otherwise carry Markdown as their emitted text format
- **AND** both SHALL be eligible for the same Markdown chunking strategy

#### Scenario: OCR diagnostics are honest

- **WHEN** a PDF result is emitted
- **THEN** metadata SHALL make it possible to distinguish whether OCR was required and whether OCR was actually used
- **AND** a result produced only by `pdf-inspector` SHALL NOT claim that the OCR worker processed the document

### Requirement: Source index identity SHALL include the resolved OCR worker fingerprint

The existing source index identity SHALL include the OCR routing configuration, the sorted unconditional routing type set, and a deterministic worker fingerprint. The fingerprint SHALL include worker availability, protocol version, package names and exact versions, pipeline identity and revision, model identity and revision, and output-schema identity and version. It SHALL exclude transient process details such as process identifiers. An unavailable worker SHALL contribute a stable unavailable fingerprint rather than an omitted field.

The worker fingerprint SHALL be recorded for every source through the existing index-identity mechanism. A change to any fingerprint field SHALL invalidate the prior identity so byte-identical sources are re-ingested. The initial payload extension used schema 4. The routing-policy amendment SHALL use schema 5 so existing identities cannot silently omit the unconditional routing set.

#### Scenario: Provisioning an unavailable worker triggers re-ingestion

- **GIVEN** a source was indexed while the worker fingerprint recorded unavailable
- **WHEN** the worker is provisioned and its capability probe succeeds
- **THEN** the source index identity SHALL change
- **AND** a byte-identical source SHALL be re-ingested rather than reported `skipped_unchanged`

#### Scenario: Worker contract or model change triggers re-ingestion

- **GIVEN** a source was indexed with one resolved worker fingerprint
- **WHEN** the protocol version, package versions, pipeline identity, model identity, or output-schema identity changes
- **THEN** the source index identity SHALL change
- **AND** a byte-identical source SHALL be re-ingested rather than reported `skipped_unchanged`

#### Scenario: Unchanged worker fingerprint preserves unchanged-source behaviour

- **GIVEN** the source bytes, OCR routing configuration, and resolved worker fingerprint are unchanged
- **WHEN** the source is ingested again
- **THEN** the worker fingerprint SHALL NOT alone prevent the existing `skipped_unchanged` result

### Requirement: The OCR routing gate SHALL be calibrated evidence expressed as injected configuration

The threshold that selects the OCR fallback SHALL be a calibrated value carried in injected configuration, not a constant in the routing module. It SHALL follow the shape the existing PDF knobs already use: top-level fields on the effective settings beside `pdf_reader` and `liteparse_ocr_enabled`, resolved once at the composition root and passed downstream.

The gate SHALL be calibrated on a committed fixture set disjoint from the fixtures used to evaluate whether the OCR fallback improves retrieval. Calibration SHALL report routing behaviour — text-based PDFs the gate would route to OCR, and OCR-required PDFs it would leave on the fast path — and SHALL NOT be the same run that measures downstream retrieval quality.

The packaged default SHALL keep the fallback off until the promotion gates are met, so "the OCR capability is available" in the routing requirement above means the worker probe succeeded **and** the operator enabled routing. `config/` SHALL NOT probe the worker, and no module SHALL read a settings singleton to obtain the gate.

#### Scenario: Routing threshold is read from injected settings

- **WHEN** the routing seam decides whether a PDF needs OCR
- **THEN** it SHALL read the gate from the injected effective settings
- **AND** the routing module SHALL NOT contain a hardcoded threshold constant

#### Scenario: Calibration and evaluation fixtures are disjoint

- **GIVEN** the committed PDF calibration fixtures and the committed PDF evaluation fixtures
- **WHEN** the OCR routing gate is calibrated
- **THEN** calibration SHALL use only the calibration fixtures
- **AND** the evaluation fixtures SHALL remain unused until the Stage 5 ablation

#### Scenario: Packaged default keeps the fallback off

- **GIVEN** a fresh installation whose operator has set no OCR routing configuration
- **AND** the isolated OCR worker is provisioned and compatible
- **WHEN** a scanned PDF is ingested
- **THEN** the OCR fallback SHALL NOT be selected
- **AND** the existing degraded `pdf-inspector` behaviour SHALL be preserved
- **AND** enabling the fallback SHALL require an explicit operator setting until the promotion gates are met
