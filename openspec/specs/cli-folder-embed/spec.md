## ADDED Requirements

### Requirement: Per-file tracking in ingestion results
The `ingest_path()` function SHALL return a `file_details` list alongside the existing `files_indexed` and `chunks_created` fields. Each entry SHALL contain `file` (str), `status` (one of `indexed`, `failed`, `skipped`), `chunks` (int, 0 for failed/skipped), and optionally `error` (str, present only when status is `failed`).

#### Scenario: Successful single file ingestion
- **WHEN** `ingest_path()` is called with a valid PDF file path
- **THEN** the return dict SHALL contain `file_details` with one entry where `status` is `"indexed"` and `chunks` is greater than 0

#### Scenario: Mixed folder with supported and unsupported files
- **WHEN** `ingest_path()` is called with a directory containing both `.pdf` and `.exe` files
- **THEN** the return dict SHALL contain `file_details` where `.pdf` files have `status "indexed"` and unsupported files do not appear (they are excluded by `_gather_supported_files`)

#### Scenario: Corrupt file in folder
- **WHEN** `ingest_path()` is called with a directory where one PDF is corrupt
- **THEN** the corrupt file SHALL have `status "failed"` with an `error` message, and other files SHALL be `status "indexed"` normally

### Requirement: Structured per-file logging
During ingestion, the CLI SHALL log one structured line per file at INFO level containing the file name, status (indexed/failed/skipped), and chunk count or error message.

#### Scenario: Logging during folder ingestion
- **WHEN** `rag-mcp ingest /path/to/folder` processes 5 files
- **THEN** stderr SHALL contain 5 INFO-level log lines, one per file, each including the file name and outcome

### Requirement: Report generation via --report flag
The `rag-mcp ingest` command SHALL accept a `--report <path>` option. When provided, the CLI SHALL write an ingestion report to the specified path after completion. The format SHALL be JSON if the path ends in `.json`, otherwise Markdown.

#### Scenario: JSON report output
- **WHEN** `rag-mcp ingest /path/to/docs --report report.json` completes successfully
- **THEN** `report.json` SHALL be a valid JSON file containing `timestamp`, `config`, `input_path`, `summary` (total, indexed, failed, skipped, chunks), and `files` array

#### Scenario: Markdown report output
- **WHEN** `rag-mcp ingest /path/to/docs --report report.md` completes successfully
- **THEN** `report.md` SHALL be a Markdown file with headers for Summary, Configuration, and Per-File Details

#### Scenario: Report on partial failure
- **WHEN** ingestion completes with some files failing
- **THEN** the report SHALL include all files — successful ones with chunk counts and failed ones with error messages

#### Scenario: No --report flag
- **WHEN** `rag-mcp ingest /path/to/docs` is run without `--report`
- **THEN** no report file is written and behaviour is identical to the current implementation

### Requirement: Report overwrites with warning
When `--report <path>` is provided and the file already exists, the CLI SHALL overwrite it and log a WARNING to stderr.

#### Scenario: Overwriting existing report
- **WHEN** `rag-mcp ingest /path/to/docs --report existing.json` is run and `existing.json` exists
- **THEN** the file is overwritten and a warning is logged to stderr

### Requirement: Integration test with real PDFs
The test suite SHALL include an integration test that ingests a folder of PDFs via the CLI and verifies the report content.

#### Scenario: Ingest 5 PDFs from test fixtures
- **WHEN** the integration test runs `rag-mcp ingest <fixture_dir> --report report.json`
- **THEN** the report SHALL list all 5 PDFs with `status "indexed"` and `chunks > 0`

### Requirement: ADR documentation
An Architectural Decision Record SHALL be added to `docs/adr/` documenting the folder embedding workflow, report format, and design rationale.

#### Scenario: ADR file exists
- **WHEN** the change is complete
- **THEN** `docs/adr/008-cli-folder-embed-progress.md` SHALL exist and contain the decision record
