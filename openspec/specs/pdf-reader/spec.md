## Purpose

Define a pluggable PDF reader architecture with environment-variable-driven backend selection, bounding-box metadata capture, graceful fallback across multiple parser backends, and structured error handling for MCP tool compliance.

## Requirements

### Requirement: PDF reader SHALL be selectable via environment variable

The system SHALL read a `PDF_READER` environment variable at config-load time and resolve it to one of the supported parser backends. Accepted values SHALL be `auto`, `liteparse`, `pypdfium2`, and `pypdf`. Any other value SHALL log a warning and fall back to `auto` resolution. The resolved backend SHALL be exposed as a `RESOLVED_PDF_READER` module-level constant in `config.py` computed exactly once at import.

#### Scenario: Explicit backend selection via env var
- **WHEN** `PDF_READER=liteparse` is set and the `liteparse` package is importable
- **THEN** `RESOLVED_PDF_READER` SHALL equal `"liteparse"` and the LiteParse adapter SHALL be used for all `.pdf` ingestion

#### Scenario: Unknown value falls back to auto with warning
- **WHEN** `PDF_READER=fastparser` (an unsupported value) is set
- **THEN** the system SHALL log a warning naming the offending value and the fallback, and SHALL resolve as if `PDF_READER=auto` had been set

#### Scenario: Resolver mirrors existing sparse-backend pattern
- **WHEN** a developer inspects `config.py`
- **THEN** the resolver structure SHALL follow the same shape as `_resolve_sparse_backend()` at `config.py:138-160`, including a private `_resolve_pdf_reader()` function and a `RESOLVED_PDF_READER` constant

### Requirement: Auto resolution SHALL probe backends in preference order with graceful fallback

When `PDF_READER=auto` (the proposed default after Experiment 11 passes), the system SHALL probe backend imports in the order `liteparse → pypdfium2 → pypdf` and SHALL select the first importable backend. PyMuPDF is structurally excluded from accepted values entirely (AGPL-3 incompatibility — see design.md Decision 4). If no optional backend is installed, the system SHALL fall back to `pypdf` (always available via `llama-index-readers-file`).

#### Scenario: LiteParse installed and selected by auto
- **WHEN** `PDF_READER=auto` is set and the `liteparse` package is importable
- **THEN** `RESOLVED_PDF_READER` SHALL equal `"liteparse"`

#### Scenario: LiteParse missing, pypdfium2 installed
- **WHEN** `PDF_READER=auto` is set, `liteparse` is not importable, and `pypdfium2` is importable
- **THEN** `RESOLVED_PDF_READER` SHALL equal `"pypdfium2"` and the system SHALL log an informational message that LiteParse was not available

#### Scenario: No optional backend installed
- **WHEN** `PDF_READER=auto` is set and neither `liteparse` nor `pypdfium2` is importable
- **THEN** `RESOLVED_PDF_READER` SHALL equal `"pypdf"` and ingestion SHALL behave identically to the pre-change pipeline

#### Scenario: Explicit backend requested but not installed
- **WHEN** `PDF_READER=liteparse` is set but `liteparse` is not importable
- **THEN** the system SHALL log an error naming the missing package and SHALL fall back to `pypdf` rather than raising

### Requirement: Default behaviour SHALL be preserved when LiteParse is not installed

Users who do not install the `[pdf-liteparse]` optional-dependency extra and do not set `PDF_READER` SHALL experience semantically equivalent ingestion behaviour to the pre-change pipeline (same source files produce same chunk counts within tolerance; not byte-identical because PDF parsing is non-deterministic across library versions). The pre-change `pypdf` via `llama-index-readers-file` path SHALL remain the implicit default until Experiment 11 passes and a follow-on change flips the default to `auto`.

#### Scenario: Baseline install with no env var
- **WHEN** the project is installed via `uv sync` (no extras) and `PDF_READER` is unset
- **THEN** `RESOLVED_PDF_READER` SHALL equal `"pypdf"` and ingestion SHALL produce the same Document objects as the pre-change pipeline

#### Scenario: Baseline install with PDF_READER=auto
- **WHEN** the project is installed via `uv sync` (no extras) and `PDF_READER=auto` is set
- **THEN** `RESOLVED_PDF_READER` SHALL equal `"pypdf"` because no optional backend is importable

### Requirement: Reader failures SHALL surface as MCP error dictionaries, never exceptions

Every PDF reader adapter SHALL wrap its underlying parser calls so that any exception (corrupt PDF, native crash, IO failure, encoding error) is caught and re-raised as a structured error dictionary matching the existing `_make_file_detail()` helper contract at `ingestion.py:54`: `{"file": "<filename>", "status": "failed", "chunks": 0, "error": "<human-readable detail>"}`. This shape is consumed directly by `ingest_path_async`'s `file_details` aggregation. Adapters SHALL NEVER raise an exception that propagates out of `ingest_documents` or any other MCP tool handler, per the project's "Never raise from MCP tool handlers" gotcha (AGENTS.md).

#### Scenario: Corrupt PDF raises inside adapter
- **WHEN** a `.pdf` file is structurally corrupt and the underlying parser raises an exception
- **THEN** the adapter SHALL catch the exception, log it with the filename, and return a structured error dictionary with `status="error"` and a descriptive message
- **AND** the exception SHALL NOT propagate to the `ingest_documents` caller

#### Scenario: LiteParse native crash
- **WHEN** the LiteParse native library crashes (segfault wrapper, FFI panic, or Rust panic propagated through `pyo3`)
- **THEN** the adapter SHALL catch the resulting Python-visible exception, log it, and return a structured error dictionary
- **AND** ingestion of subsequent files in the same batch SHALL continue uninterrupted

#### Scenario: Error contract matches _make_file_detail shape
- **WHEN** any reader adapter catches an exception and constructs an error dictionary
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

The system SHALL expose a `BaseReader` protocol in `src/rag_mcp/integrations/pdf/base.py` defining the contract every PDF adapter must implement. New adapters SHALL be addable by creating a single module in `src/rag_mcp/integrations/pdf/` and registering it in the factory's resolution map. The ingestion loader call site SHALL NOT require modification when a new reader is added; only `config.py` (env var accepted values) and the factory map SHALL change.

The former `src/rag_mcp/readers/` package SHALL resolve via a deprecated re-export shim (removal scheduled for v2.0.0) so existing `from rag_mcp.readers import ...` consumers keep working with a `DeprecationWarning`.

#### Scenario: Adding a new adapter
- **WHEN** a developer creates `src/rag_mcp/integrations/pdf/spdf.py` implementing `BaseReader` and adds `"spdf"` to the accepted values in `config.py`
- **THEN** no other source file SHALL require modification to make `PDF_READER=spdf` functional

#### Scenario: Factory returns adapter, not reader instance
- **WHEN** `get_pdf_reader()` is called
- **THEN** it SHALL return a callable (typically a LlamaIndex-compatible reader class or a closure wrapping one), not a parsed-document instance, so `SimpleDirectoryReader(file_extractor={".pdf": get_pdf_reader()})` works at the ingestion loader call site

#### Scenario: Legacy readers import path resolves
- **WHEN** code executes `from rag_mcp.readers import get_pdf_reader` (or any other former `readers/` export)
- **THEN** the import SHALL succeed via the deprecated shim
- **AND** a `DeprecationWarning` SHALL be emitted naming `rag_mcp.integrations.pdf` as the new path

#### Scenario: Factory dispatch behaviour unchanged
- **WHEN** the `auto` backend resolution runs after the relocation
- **THEN** backend preference order, graceful fallback, and `PDF_READER` env var handling SHALL be identical to the pre-refactor factory (ADR-020 amended for location only)

### Requirement: LiteParse SHALL be a core dependency

The `liteparse` package SHALL be declared in the main `[project.dependencies]`
list in `pyproject.toml`, not as an optional extra. The base `uv sync` SHALL
install `liteparse` and make it available for PDF parsing. The `auto`
resolution order SHALL prefer LiteParse when importable.

#### Scenario: Baseline install includes liteparse
- **WHEN** a user runs `uv sync` without any extras
- **THEN** the `liteparse` package SHALL be importable
- **AND** `RESOLVED_PDF_READER` SHALL resolve to `"liteparse"`

#### Scenario: Explicit override to pypdf
- **WHEN** a user sets `PDF_READER=pypdf` in `.env`
- **THEN** the system SHALL use pypdf regardless of LiteParse being installed

### Requirement: PDF reader default SHALL be auto after Experiment 11 validation

The default value for `PDF_READER` SHALL be `auto`. When `auto` is selected
and `liteparse` is installed, the system SHALL resolve to LiteParse. When
LiteParse is not installed, the system SHALL fall back to pypdf. Experiment 11
validated this adoption (+6.9% nDCG@10); see ADR-020 for the decision record.

#### Scenario: Auto default (current state)
- **WHEN** no `PDF_READER` env var is set and `liteparse` is installed
- **THEN** `RESOLVED_PDF_READER` SHALL resolve to `"liteparse"`

#### Scenario: Auto fallback when LiteParse not installed
- **WHEN** no `PDF_READER` env var is set and `liteparse` is NOT installed
- **THEN** `RESOLVED_PDF_READER` SHALL resolve to `"pypdf"` (always available)
