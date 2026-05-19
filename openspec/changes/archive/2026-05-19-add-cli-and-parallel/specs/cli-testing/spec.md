# CLI Testing Capability Specification

## ADDED Requirements

### Requirement: CLI commands have automated test coverage

The system SHALL have automated test coverage for all CLI subcommands (`ingest`,
`search`, `list`) exercised through Typer's `CliRunner`.

#### Scenario: Ingest command tested via CliRunner

- **GIVEN** the conftest fixtures mock ChromaDB and the embedding model
- **WHEN** `runner.invoke(app, ["ingest", "test.txt"])` is called
- **THEN** the result SHALL have `exit_code == 0`
- **AND** the output SHALL contain a success message with file and chunk counts

#### Scenario: Search command tested via CliRunner

- **GIVEN** documents have been indexed via `ingest_path()`
- **WHEN** `runner.invoke(app, ["search", "test query"])` is called
- **THEN** the result SHALL have `exit_code == 0`
- **AND** the output SHALL contain result entries in a Rich table

#### Scenario: List command tested via CliRunner

- **GIVEN** documents have been indexed
- **WHEN** `runner.invoke(app, ["list"])` is called
- **THEN** the result SHALL have `exit_code == 0`
- **AND** the output SHALL contain document sources and chunk counts

### Requirement: JSON output mode is tested on all commands

Every command's `--json` flag SHALL be tested to produce valid JSON output
with the correct schema.

#### Scenario: JSON output on success

- **GIVEN** a valid ingest operation
- **WHEN** `runner.invoke(app, ["ingest", "test.txt", "--json"])` is called
- **THEN** the stdout output SHALL parse as valid JSON
- **AND** the JSON SHALL contain `"status"` (string), `"files_indexed"` (int),
  and `"chunks_created"` (int) keys

#### Scenario: JSON output on error

- **GIVEN** a non-existent path
- **WHEN** `runner.invoke(app, ["ingest", "/nonexistent/", "--json"])` is called
- **THEN** stdout or stderr SHALL contain valid JSON with `"status": "error"`

#### Scenario: JSON output for empty search

- **GIVEN** no documents indexed
- **WHEN** `runner.invoke(app, ["search", "anything", "--json"])` is called
- **THEN** the output SHALL be `"[]"` (empty JSON array string)

### Requirement: Progress reporting has automated coverage

Both Rich (TTY) and plain-text (non-TTY) progress modes SHALL be tested.

#### Scenario: Plain-text progress in non-TTY mode

- **GIVEN** stdout is not a terminal (CliRunner default)
- **WHEN** `runner.invoke(app, ["ingest", "test.txt"])` is called
- **THEN** stderr SHALL contain `"Reading file"` progress messages
- **AND** stderr SHALL contain `"Embedding"` progress messages

#### Scenario: JSON mode suppresses progress output

- **GIVEN** the `--json` flag is set
- **WHEN** `runner.invoke(app, ["ingest", "test.txt", "--json"])` is called
- **THEN** no `"Reading file"` or `"Embedding"` text SHALL appear in stderr
  (only JSON output)

### Requirement: Exit codes reflect execution status

Exit codes SHALL be tested for success (0), error (1), and interrupt (130)
scenarios.

#### Scenario: Success exit code

- **GIVEN** a valid file path
- **WHEN** `rag-mcp ingest valid.txt` is invoked via CliRunner
- **THEN** `result.exit_code` SHALL equal 0

#### Scenario: Error exit code

- **GIVEN** a non-existent path
- **WHEN** `rag-mcp ingest /nonexistent/` is invoked via CliRunner
- **THEN** `result.exit_code` SHALL not equal 0

### Requirement: CLI `--help` is testable

All subcommands SHALL have `--help` output that documents their options
and can be asserted in tests.

#### Scenario: Top-level help lists subcommands

- **WHEN** `runner.invoke(app, ["--help"])` is called
- **THEN** the output SHALL contain `"ingest"`, `"search"`, and `"list"`

#### Scenario: Subcommand help lists options

- **WHEN** `runner.invoke(app, ["ingest", "--help"])` is called
- **THEN** the output SHALL contain `"--workers"`, `"--chunk-size"`,
  `"--chunk-overlap"`, and `"--json"`

### Requirement: Concurrent write lock is tested with actual threads

The `_write_lock` (`threading.Lock`) in `ingestion.py` SHALL be tested to
ensure it serialises ChromaDB writes when multiple threads attempt to enter
the critical section simultaneously.

#### Scenario: Lock serialises concurrent writers

- **GIVEN** `_write_lock` is available and unheld
- **WHEN** two threads attempt to acquire `_write_lock` simultaneously
- **THEN** at most one thread SHALL be executing the critical section at any time

### Requirement: BoundedSemaphore throttles concurrent embedding calls

The `_embed_semaphore` (`threading.BoundedSemaphore(2)`) SHALL be tested to
ensure it limits concurrent embedding API calls to the configured limit.

#### Scenario: Semaphore limits concurrency to 2

- **GIVEN** `EMBED_CONCURRENCY=2`
- **WHEN** 4 threads attempt to acquire the semaphore simultaneously
- **THEN** at most 2 threads SHALL hold the semaphore at any time

### Requirement: Parallel shutdown cancels pending futures

When `_shutdown_requested` is set during parallel ingestion, the
`ThreadPoolExecutor` SHALL be shut down with `cancel_futures=True`.

#### Scenario: Shutdown cancels pending work

- **GIVEN** parallel ingestion is in progress with multiple files queued
- **AND** `_shutdown_requested` is set mid-processing
- **WHEN** the event loop checks the flag
- **THEN** `pool.shutdown(wait=False, cancel_futures=True)` SHALL be called
- **AND** no further files SHALL be processed

### Requirement: Path resolution is tested

The `ingest_path()` function's path resolution (`expanduser().resolve()`) SHALL
be tested with tilde expansion and relative path traversal.

#### Scenario: Tilde expansion

- **GIVEN** a file exists at `~/test_file.txt`
- **WHEN** `ingest_path("~/test_file.txt")` is called
- **THEN** `Path(path).expanduser().resolve()` SHALL resolve the tilde to the
  user's home directory

### Requirement: ANSI sanitisation has isolated unit tests

The `_sanitise_display_name()` function in `cli.py` SHALL have dedicated unit
tests for common ANSI escape sequences.

#### Scenario: Colour codes stripped

- **GIVEN** a string `"\x1b[32mgreen\x1b[0m"`
- **WHEN** `_sanitise_display_name()` is called
- **THEN** the result SHALL be `"green"`

#### Scenario: Plain text passes through

- **GIVEN** a string `"normal text"`
- **WHEN** `_sanitise_display_name()` is called
- **THEN** the result SHALL be `"normal text"`
