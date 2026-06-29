## Purpose

Define the Azure Document Intelligence integration contract — optional hybrid deployment mode where document parsing uses Azure for structured table/layout extraction while embeddings, code graph, and search remain fully local.

## Requirements

### Requirement: DOCUMENT_BACKEND configuration flag

The system SHALL read a `DOCUMENT_BACKEND` environment variable from `.env` with accepted values `"local"` (default) and `"azure"`. The value SHALL be validated at config load time. Unknown values SHALL log a warning and fall back to `"local"`.

#### Scenario: Default is local

- **WHEN** `DOCUMENT_BACKEND` is not set in `.env`
- **THEN** `config.DOCUMENT_BACKEND` SHALL equal `"local"`
- **THEN** document parsing SHALL use the existing LiteParse → pypdfium2 → pypdf chain

#### Scenario: Azure mode configured

- **WHEN** `DOCUMENT_BACKEND=azure` is set with valid Azure credentials
- **THEN** `config.DOCUMENT_BACKEND` SHALL equal `"azure"`
- **THEN** document parsing SHALL use Azure Document Intelligence

#### Scenario: Unknown value falls back

- **WHEN** `DOCUMENT_BACKEND=google` (unsupported) is set
- **THEN** the system SHALL log a warning and use `"local"` mode

### Requirement: Azure Document Intelligence integration

When `DOCUMENT_BACKEND=azure`, the system SHALL use the Azure AI Document Intelligence SDK (`azure-ai-documentintelligence`) to parse document files (PDF, DOCX). The system SHALL send the document to the configured Azure endpoint and receive structured JSON containing paragraphs with roles, tables with cell structure, and key-value pairs.

#### Scenario: PDF parsed via Azure

- **WHEN** a PDF file is ingested with `DOCUMENT_BACKEND=azure`
- **THEN** the system SHALL send the PDF to Azure Document Intelligence using the configured `AZURE_DOC_INTELLIGENCE_MODEL` (default `prebuilt-layout`)
- **THEN** the system SHALL receive structured JSON with paragraphs, tables, and metadata

#### Scenario: Azure credentials configured

- **WHEN** `DOCUMENT_BACKEND=azure` is set
- **THEN** `AZURE_DOC_INTELLIGENCE_ENDPOINT` and `AZURE_DOC_INTELLIGENCE_KEY` SHALL be read from `.env`
- **THEN** these credentials SHALL NOT be logged or exposed in error messages

### Requirement: Table-aware chunking from Azure output

When Azure returns structured table data, the system SHALL chunk tables as intact units — a table SHALL NOT be split across multiple chunks. Table chunks SHALL carry `content_type: "table"` metadata in ChromaDB.

#### Scenario: Table preserved as single chunk

- **WHEN** Azure detects a 10-row table in a PDF
- **THEN** the entire table SHALL be stored as a single chunk with `metadata["content_type"] = "table"`
- **THEN** the chunk text SHALL include row/column structure in a readable format

#### Scenario: Large table handling

- **WHEN** Azure detects a table with 50+ rows that exceeds the chunk size limit
- **THEN** the table SHALL be split into row groups of configurable size (default 25 rows)
- **THEN** each row group SHALL carry `metadata["table_part"] = "1 of 2"` (or similar)

### Requirement: Graceful fallback when Azure fails

When `DOCUMENT_BACKEND=azure` is set but Azure is unreachable (network error, rate limit, authentication failure), the system SHALL automatically fall back to the existing LiteParse → pypdfium2 → pypdf chain. The fallback SHALL be logged as a warning, not an error.

#### Scenario: Azure network failure

- **WHEN** Azure Document Intelligence is unreachable (timeout, DNS failure)
- **THEN** the system SHALL fall back to the LiteParse PDF reader chain
- **THEN** a warning SHALL be logged: "Azure Document Intelligence unavailable, falling back to local parsing"
- **THEN** ingestion SHALL continue without interruption

#### Scenario: Azure credentials missing

- **WHEN** `DOCUMENT_BACKEND=azure` is set but `AZURE_DOC_INTELLIGENCE_ENDPOINT` or `AZURE_DOC_INTELLIGENCE_KEY` is empty
- **THEN** the system SHALL fall back to `"local"` mode at config load time
- **THEN** a warning SHALL be logged indicating missing credentials

#### Scenario: Azure rate limit exceeded

- **WHEN** Azure returns HTTP 429 (rate limit)
- **THEN** the system SHALL retry once after a 5-second delay
- **THEN** if the retry fails, the system SHALL fall back to local parsing for that file

### Requirement: Azure SDK as optional dependency

The `azure-ai-documentintelligence` package SHALL be declared as an optional extra in `pyproject.toml` (e.g., `[project.optional-dependencies] azure = ["azure-ai-documentintelligence"]`). The package SHALL NOT be installed by default `uv sync`. Import SHALL be guarded at runtime.

#### Scenario: Base install without Azure

- **WHEN** a user runs `uv sync` (no extras)
- **THEN** `azure-ai-documentintelligence` SHALL NOT be installed
- **THEN** `DOCUMENT_BACKEND=local` SHALL work without error

#### Scenario: Azure extra installed

- **WHEN** a user runs `uv sync --extra azure`
- **THEN** `azure-ai-documentintelligence` SHALL be installed
- **THEN** `DOCUMENT_BACKEND=azure` SHALL be functional

#### Scenario: Azure mode without SDK installed

- **WHEN** `DOCUMENT_BACKEND=azure` is set but the Azure SDK is not installed
- **THEN** the system SHALL log a warning and fall back to `"local"` mode
- **THEN** no `ImportError` SHALL propagate to the user

### Requirement: azure_reader module isolation

The Azure integration SHALL be contained in a single `azure_reader.py` module. This module SHALL NOT be imported by any other module at the top level — it SHALL be lazily imported only when `DOCUMENT_BACKEND=azure`. This ensures zero import-time overhead for local-only users.

#### Scenario: Local mode no Azure import

- **WHEN** `DOCUMENT_BACKEND=local` is configured
- **THEN** `azure_reader.py` SHALL NOT be imported at any point during execution
- **THEN** the Azure SDK need not be installed
