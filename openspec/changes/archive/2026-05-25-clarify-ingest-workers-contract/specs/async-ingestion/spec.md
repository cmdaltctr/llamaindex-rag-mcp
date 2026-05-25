## MODIFIED Requirements

### Requirement: CLI wraps async ingest
The CLI subcommand `rag-mcp ingest` SHALL invoke `ingest_path_async(...)` via `asyncio.run(...)` at the entry point. CLI flags, output format, exit codes, and report generation SHALL describe only controls that affect current async ingestion behavior. The CLI SHALL NOT present a file-reader `--workers` option as effective unless file-level parallel reading is implemented.

#### Scenario: CLI ingest uses async entry point
- **WHEN** the user runs `rag-mcp ingest /path/to/docs`
- **THEN** the CLI SHALL invoke `asyncio.run(ingest_path_async("/path/to/docs"))`
- **THEN** stderr output, exit code, and `--report` output SHALL reflect the async implementation

#### Scenario: Ingest help omits ineffective workers option
- **WHEN** the user runs `rag-mcp ingest --help`
- **THEN** the help output SHALL NOT advertise file-reader workers as an effective throughput control
- **THEN** the help output SHALL continue to document effective chunking, collection, report, and JSON options

#### Scenario: Ingest report omits ineffective workers setting
- **WHEN** `rag-mcp ingest /docs --report report.json` runs
- **THEN** the generated report SHALL NOT claim a file-reader worker count affected the run
- **THEN** the report MAY include effective embedding batch size and embedding concurrency settings
