## MODIFIED Requirements

### Requirement: PDF reader SHALL be selectable via environment variable

The system SHALL read a `PDF_READER` environment variable at config-load
time into the frozen `Settings.pdf_reader` field. Accepted values SHALL be
`auto`, `liteparse`, `pypdfium2`, and `pypdf`. Any other value SHALL log a
warning naming the offending value and fall back to `auto`. The composition
root SHALL resolve `auto` to a concrete backend name exactly once at startup
and bake the result into the injected `EffectiveSettings.pdf_reader`; no
module-level resolved constant exists.

#### Scenario: Explicit backend selection via env var

- **WHEN** `PDF_READER=liteparse` is set and the `liteparse` package is importable
- **THEN** the injected `EffectiveSettings.pdf_reader` SHALL equal `"liteparse"` and the LiteParse adapter SHALL be used for all `.pdf` ingestion

#### Scenario: Unknown value falls back to auto with warning

- **WHEN** `PDF_READER=fastparser` (an unsupported value) is set
- **THEN** the system SHALL log a warning naming the offending value and the fallback, and SHALL resolve as if `PDF_READER=auto` had been set

#### Scenario: Resolution happens once at the composition root

- **WHEN** the server or CLI entry point starts
- **THEN** `compose.resolve_pdf_reader` SHALL run once over the frozen settings
- **AND** every operation below the entry point SHALL read the concrete name from its injected settings, with no repeated probing

### Requirement: Reader failures SHALL surface as MCP error dictionaries, never exceptions

The ingestion pipeline SHALL catch every per-file reader failure (corrupt
PDF, native crash, IO failure, encoding error) around the chunking stage
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

### Requirement: Reader factory SHALL be extensible without modifying ingestion code

New reader adapters SHALL be addable by creating a single module in
`src/rag_mcp/integrations/pdf/` and registering it with one
`registry.register()` call. The shared contract is the duck-typed
`load_data(file) -> list[Document]` method — there is no separate protocol
module. The ingestion call sites SHALL NOT require modification when a new
reader is added; only the accepted values in `config/` and the registry
registration SHALL change. The factory receives the reader name from its
caller: `get_pdf_reader(reader)`.

#### Scenario: Adding a new adapter

- **WHEN** a developer creates `src/rag_mcp/integrations/pdf/spdf.py` with a `load_data` method and adds `"spdf"` to the accepted values in `config/` plus one `register("spdf", "...")` call in the registry
- **THEN** no other source file SHALL require modification to make `PDF_READER=spdf` functional

#### Scenario: Factory returns adapter, not reader instance

- **WHEN** `get_pdf_reader(reader)` is called with a concrete reader name
- **THEN** it SHALL return an adapter instance with a `load_data` method, not a parsed-document instance, so `SimpleDirectoryReader(file_extractor={".pdf": get_pdf_reader(resolved.pdf_reader)})` works at the ingestion call site

#### Scenario: Factory dispatch behaviour unchanged

- **WHEN** the `auto` backend resolution runs after the relocation
- **THEN** backend preference order, graceful fallback, and `PDF_READER` env var handling SHALL be identical to the pre-refactor factory (ADR-020 amended for location only)

### Requirement: PDF reader default SHALL be auto after Experiment 11 validation

The default value for `PDF_READER` SHALL be `auto`. When `auto` is selected
and `liteparse` is installed, the system SHALL resolve to LiteParse. When
LiteParse is not installed, the system SHALL fall back to pypdf. Experiment
11 validated this adoption (+6.9% nDCG@10); see ADR-020 for the decision
record.

#### Scenario: Auto default (current state)

- **WHEN** no `PDF_READER` env var is set and `liteparse` is installed
- **THEN** the resolved reader SHALL be `"liteparse"`

#### Scenario: Auto fallback when LiteParse not installed

- **WHEN** no `PDF_READER` env var is set and `liteparse` is NOT installed
- **THEN** the resolved reader SHALL be `"pypdf"` (always available)

## REMOVED Requirements

### Requirement: Default behaviour SHALL be preserved when LiteParse is not installed

**Reason:** Obsolete transition requirement. It describes a pre-Experiment-11
state (`[pdf-liteparse]` optional extra, pypdf implicit default, "until
Experiment 11 passes") that two later requirements in this same spec already
superseded: liteparse is a core dependency (base `uv sync` installs it) and
the default is `auto`. Its scenarios contradict the core-dependency
requirement by assuming no optional backend is importable on a baseline
install.

**Migration:** None. The core-dependency requirement (baseline install
includes liteparse) and the auto-default requirement fully describe current
behaviour; no consumer depends on the transition text.
