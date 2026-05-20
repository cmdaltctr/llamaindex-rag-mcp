# Specification: document-deletion

## Requirements

### Requirement: Delete chunks by source file path

The system SHALL provide a `remove_document(file_path: str, collection_name: str = "documents") -> dict` function in `ingestion.py` that deletes all chunks whose `file_path` metadata matches the given path. The function SHALL be idempotent — calling it on a file with no indexed chunks SHALL return success with `chunks_removed: 0`.

#### Scenario: Delete existing file chunks
- **WHEN** `remove_document("/path/to/file.pdf", collection_name="research")` is called on a file with 12 indexed chunks
- **THEN** all 12 chunks SHALL be removed from the `"research"` collection
- **THEN** the result SHALL include `"chunks_removed": 12` and `"status": "ok"`

#### Scenario: Delete non-existent file chunks
- **WHEN** `remove_document("/path/to/unknown.pdf")` is called
- **THEN** the result SHALL include `"chunks_removed": 0` and `"status": "ok"`
- **THEN** no error SHALL be raised

#### Scenario: Delete from non-existent collection
- **WHEN** `remove_document("/path/to/file.pdf", collection_name="nonexistent")` is called
- **THEN** the result SHALL include `"status": "error"` and a descriptive message

### Requirement: Delete chunks by metadata filter

The system SHALL provide a `remove_by_metadata(metadata_filter: dict, collection_name: str = "documents") -> dict` function in `ingestion.py` that deletes all chunks matching an arbitrary ChromaDB `where` filter.

#### Scenario: Delete by category filter
- **WHEN** `remove_by_metadata({"category": "uncategorised"}, collection_name="research")` is called
- **THEN** all chunks with `category = "uncategorised"` SHALL be removed from the `"research"` collection
- **THEN** the result SHALL include `"chunks_removed"` count

#### Scenario: Delete by empty filter
- **WHEN** `remove_by_metadata({})` is called
- **THEN** the function SHALL raise `ValueError` or return an error result (ChromaDB rejects empty where clauses)

### Requirement: Drop (delete) a collection

The system SHALL provide a `remove_collection(collection_name: str) -> dict` function in `ingestion.py` that permanently deletes an entire ChromaDB collection.

#### Scenario: Drop existing collection
- **WHEN** `remove_collection("research")` is called on an existing collection
- **THEN** the `"research"` collection SHALL be permanently removed
- **THEN** subsequent `list_collections()` SHALL NOT include `"research"`

#### Scenario: Drop non-existent collection
- **WHEN** `remove_collection("nonexistent")` is called
- **THEN** the result SHALL include `"status": "error"` and a descriptive message

### Requirement: Re-ingestion replaces old chunks (upsert semantics)

When `ingest_path()` processes a file, it SHALL call `remove_document()` for that file path BEFORE reading and chunking. This ensures re-ingesting the same file replaces its old chunks rather than appending duplicates.

#### Scenario: Re-ingest replaces chunks
- **WHEN** `ingest_path("paper.pdf", collection_name="research")` is called on a file that was previously indexed with 8 chunks
- **THEN** the old 8 chunks SHALL be removed before the new chunks are written
- **THEN** the result SHALL include `"chunks_created"` (new count) and `"chunks_removed": 8`

#### Scenario: First-time ingest has nothing to remove
- **WHEN** `ingest_path("new_file.pdf")` is called on a file never indexed before
- **THEN** `remove_document()` SHALL be called but return `chunks_removed: 0` (no-op)

### Requirement: CLI delete subcommand

The `rag-mcp` CLI SHALL provide a `delete` subcommand with three mutually-exclusive flags: `--path`, `--metadata`, and `--collection`. A `--dry-run` flag SHALL preview what would be deleted without executing. Only `--collection` SHALL require confirmation (it drops the entire collection), unless `--yes` is passed.

#### Scenario: Delete by file path via CLI
- **WHEN** `rag-mcp delete --path /path/to/file.pdf --collection research` is executed
- **THEN** all chunks for that file SHALL be removed from the `"research"` collection
- **THEN** the CLI SHALL display the number of chunks removed

#### Scenario: Delete by metadata filter via CLI
- **WHEN** `rag-mcp delete --metadata '{"category":"uncategorised"}'` is executed
- **THEN** all chunks matching that metadata SHALL be removed
- **THEN** the CLI SHALL display the number of chunks removed

#### Scenario: Drop collection via CLI
- **WHEN** `rag-mcp delete --collection research` is executed
- **THEN** the CLI SHALL ask for confirmation: "Delete entire collection 'research'? This cannot be undone. [y/N]:"
- **THEN** on confirmation, the collection SHALL be permanently dropped

#### Scenario: Drop collection with --yes flag
- **WHEN** `rag-mcp delete --collection research --yes` is executed
- **THEN** the collection SHALL be dropped immediately without confirmation prompt

#### Scenario: Dry run preview
- **WHEN** `rag-mcp delete --path /file.pdf --dry-run` is executed
- **THEN** the CLI SHALL display "Would delete N chunks" but SHALL NOT modify ChromaDB

#### Scenario: Validation — exactly one flag must be provided
- **WHEN** `rag-mcp delete` is executed with no flags, or with multiple mutually-exclusive flags
- **THEN** the CLI SHALL print an error message and exit with a non-zero status code

### Requirement: MCP delete_documents tool

The system SHALL expose a `delete_documents` MCP tool that accepts optional `path: str`, `metadata_filter: dict`, `collection: str` (default `"documents"`), and `dry_run: bool` (default `false`) parameters. When `collection` is provided without `path` or `metadata_filter`, the collection itself SHALL be dropped.

#### Scenario: MCP delete by file path
- **WHEN** `delete_documents(path="/path/to/file.pdf", collection="research")` is called via MCP
- **THEN** all chunks for that file SHALL be removed and the result SHALL include `"chunks_removed"`

#### Scenario: MCP delete by metadata filter
- **WHEN** `delete_documents(metadata_filter={"category": "uncategorised"})` is called via MCP
- **THEN** all matching chunks SHALL be removed

#### Scenario: MCP drop collection
- **WHEN** `delete_documents(collection="research")` is called via MCP (no `path` or `metadata_filter`)
- **THEN** the `"research"` collection SHALL be permanently dropped
- **THEN** the result SHALL include `"status": "ok"` and `"collection": "research"`

#### Scenario: MCP dry run
- **WHEN** `delete_documents(path="/file.pdf", dry_run=true)` is called via MCP
- **THEN** the result SHALL include `"would_delete": N` but no chunks SHALL be removed
