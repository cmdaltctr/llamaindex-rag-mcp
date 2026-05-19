# CLI Capability Specification

## ADDED Requirements

### Requirement: CLI entry point with subcommands

The system SHALL provide a single `rag-mcp` command-line entry point that
delegates to subcommands (`ingest`, `search`, `list`) when arguments are
present, and starts the MCP stdio server when invoked with no arguments.

#### Scenario: No arguments starts MCP server (backward compatible)

- **GIVEN** the `rag-mcp` command is installed
- **WHEN** it is invoked with no arguments: `uv run rag-mcp`
- **THEN** the MCP stdio server SHALL start (unchanged behaviour)

#### Scenario: Subcommand triggers CLI mode

- **GIVEN** the `rag-mcp` command is installed
- **WHEN** it is invoked with a subcommand: `uv run rag-mcp ingest ./docs/`
- **THEN** the Typer CLI SHALL process the subcommand

#### Scenario: Unknown subcommand shows help

- **GIVEN** the `rag-mcp` command is installed
- **WHEN** it is invoked with an unrecognised argument
- **THEN** a helpful error message SHALL be printed to stderr
- **AND** the exit code SHALL be non-zero

### Requirement: `ingest` subcommand

The system SHALL provide a `rag-mcp ingest <path>` command that indexes a file
or directory into the RAG vector store.

#### Scenario: Ingest a single file

- **GIVEN** a PDF file exists at `/tmp/test.pdf`
- **AND** Ollama is running with `nomic-embed-text` available
- **WHEN** `rag-mcp ingest /tmp/test.pdf` is invoked
- **THEN** the file SHALL be indexed into ChromaDB
- **AND** a success message SHALL be printed with files indexed and chunks created
- **AND** the exit code SHALL be 0

#### Scenario: Ingest a directory with subdirectories

- **GIVEN** a directory at `/tmp/docs/` containing nested subdirectories with PDFs
- **WHEN** `rag-mcp ingest /tmp/docs/` is invoked
- **THEN** all supported files in all subdirectories SHALL be discovered
- **AND** all discovered files SHALL be indexed
- **AND** the exit code SHALL be 0

#### Scenario: Path does not exist

- **GIVEN** a path `/tmp/nonexistent/` that does not exist
- **WHEN** `rag-mcp ingest /tmp/nonexistent/` is invoked
- **THEN** an error message SHALL be printed to stderr
- **AND** the exit code SHALL be non-zero

#### Scenario: Path validation — traversal attempt

- **GIVEN** a path `../../../etc/passwd` resolves outside working directory
- **WHEN** `rag-mcp ingest ../../../etc/passwd` is invoked
- **THEN** the resolved absolute path SHALL be checked for existence
- **AND** if the path does not exist or is outside accessible directories, an error SHALL be printed

#### Scenario: Ingest supports configurable chunk size

- **GIVEN** the `--chunk-size` option is provided
- **WHEN** `rag-mcp ingest ./docs/ --chunk-size 256` is invoked
- **THEN** the text splitter SHALL use chunk_size=256 for this ingestion
- **AND** the env var `CHUNK_SIZE` SHALL NOT be overridden for subsequent calls

#### Scenario: Ingest supports configurable workers

- **GIVEN** the `--workers` option is provided
- **WHEN** `rag-mcp ingest ./docs/ --workers 8` is invoked
- **THEN** file reading and chunking SHALL use up to 8 concurrent workers

### Requirement: `search` subcommand

The system SHALL provide a `rag-mcp search <query>` command that searches the
RAG vector store and prints results.

#### Scenario: Basic search

- **GIVEN** documents have been indexed into the vector store
- **AND** Ollama is running
- **WHEN** `rag-mcp search "quantum computing"` is invoked
- **THEN** the top 5 matching chunks SHALL be printed with score, source, and text
- **AND** results SHALL be sorted by descending score

#### Scenario: Search with custom top_k

- **GIVEN** documents have been indexed
- **WHEN** `rag-mcp search "quantum computing" --top-k 10` is invoked
- **THEN** up to 10 results SHALL be returned

#### Scenario: Search with threshold

- **GIVEN** documents have been indexed
- **WHEN** `rag-mcp search "quantum computing" --threshold 0.3` is invoked
- **THEN** only results with score >= 0.3 SHALL be included

#### Scenario: Search with reranking

- **GIVEN** documents have been indexed
- **WHEN** `rag-mcp search "quantum computing" --rerank` is invoked
- **THEN** results SHALL be re-scored by the cross-encoder reranker
- **AND** the `reranked` field SHALL be printed as True

#### Scenario: Empty store search

- **GIVEN** no documents have been indexed
- **WHEN** `rag-mcp search "anything"` is invoked
- **THEN** a message indicating "no results" SHALL be printed
- **AND** the exit code SHALL be 0

### Requirement: `list` subcommand

The system SHALL provide a `rag-mcp list` command that displays all indexed
documents with their chunk counts.

#### Scenario: List after ingestion

- **GIVEN** 3 PDF files have been indexed, producing 15, 8, and 22 chunks
- **WHEN** `rag-mcp list` is invoked
- **THEN** a table or list SHALL be printed with each source file and its chunk count
- **AND** the total file count and chunk count SHALL be displayed

#### Scenario: List empty store

- **GIVEN** no documents have been indexed
- **WHEN** `rag-mcp list` is invoked
- **THEN** a message indicating "no indexed documents" SHALL be printed
- **AND** the exit code SHALL be 0

### Requirement: `--help` discoverability

Every subcommand SHALL have a `--help` flag that displays usage, available
options, and defaults.

#### Scenario: Top-level help

- **WHEN** `rag-mcp --help` is invoked
- **THEN** available subcommands (`ingest`, `search`, `list`) SHALL be listed
- **AND** env var configuration SHALL be documented

#### Scenario: Subcommand help

- **WHEN** `rag-mcp ingest --help` is invoked
- **THEN** the `path` argument and all options (`--workers`, `--chunk-size`,
  `--chunk-overlap`) SHALL be documented with their defaults

### Requirement: Shell completion

The system SHALL support shell tab-completion via Typer's `--install-completion`
flag for Bash, Zsh, Fish, and PowerShell.

#### Scenario: Install Zsh completion

- **GIVEN** the user is running Zsh
- **WHEN** `rag-mcp --install-completion` is invoked
- **THEN** completion scripts SHALL be generated
- **AND** instructions for sourcing them SHALL be printed

### Requirement: Non-TTY graceful degradation

When stdout is not a TTY (piped, redirected, or in CI), progress bars SHALL
be suppressed and replaced with plain-text progress lines.

#### Scenario: Piped output

- **GIVEN** ingestion is in progress
- **WHEN** stdout is a pipe: `rag-mcp ingest ./docs/ | tee log.txt`
- **THEN** progress SHALL be printed as "Processing file N/M..." lines
- **AND** no ANSI escape codes SHALL be emitted

## MODIFIED Requirements

_None. Existing MCP tool interfaces remain unchanged._

## REMOVED Requirements

_None._
