# Specification: document-deletion

## Purpose

Define document deletion, collection deletion, re-ingestion cleanup, and dry-run preview behaviour across shared ingestion logic, the CLI, and the MCP delete tool.
## Requirements
### Requirement: Delete chunks by source file path

The system SHALL provide a
`core/ingestion/writer.py::remove_document(file_path: str,
collection_name: str = "documents") -> dict` function that applies the same
canonical path resolution and deterministic `source_id` derivation as
production ingestion, then deletes all chunks whose `source_id` matches. The
function SHALL be idempotent: calling it for a source with no indexed chunks
SHALL return success with `chunks_removed: 0`. The existing general metadata
deletion operation MAY delete a source directly with a `source_id` filter.

#### Scenario: Delete existing file chunks

- **WHEN** `remove_document("/path/to/file.pdf", collection_name="research")` is called on a source with 12 indexed chunks
- **THEN** the function MUST derive the same `source_id` used during ingestion
- **AND** all 12 chunks for that `source_id` SHALL be removed from the `"research"` collection
- **AND** the result SHALL include `"chunks_removed": 12` and `"status": "ok"`

#### Scenario: Delete non-existent file chunks

- **WHEN** `remove_document("/path/to/unknown.pdf")` is called
- **THEN** the result SHALL include `"chunks_removed": 0` and `"status": "ok"`
- **AND** no error SHALL be raised

#### Scenario: Delete from non-existent collection

- **WHEN** `remove_document("/path/to/file.pdf", collection_name="nonexistent")` is called
- **THEN** the result SHALL include `"status": "error"` and a descriptive message

### Requirement: Delete chunks by metadata filter

The system SHALL provide a
`core/ingestion/writer.py::remove_by_metadata(metadata_filter: dict,
collection_name: str = "documents") -> dict` function that deletes all chunks
matching an arbitrary store-compatible `where` filter.

#### Scenario: Delete by category filter
- **WHEN** `remove_by_metadata({"category": "uncategorised"}, collection_name="research")` is called
- **THEN** all chunks with `category = "uncategorised"` SHALL be removed from the `"research"` collection
- **THEN** the result SHALL include `"chunks_removed"` count

#### Scenario: Delete by empty filter
- **WHEN** `remove_by_metadata({})` is called
- **THEN** the function SHALL return an error result

### Requirement: Drop (delete) a collection

The system SHALL provide a
`core/ingestion/writer.py::remove_collection(collection_name: str) -> dict`
function that permanently deletes an entire configured vector-store collection.

#### Scenario: Drop existing collection
- **WHEN** `remove_collection("research")` is called on an existing collection
- **THEN** the `"research"` collection SHALL be permanently removed
- **THEN** subsequent `list_collections()` SHALL NOT include `"research"`

#### Scenario: Drop non-existent collection
- **WHEN** `remove_collection("nonexistent")` is called
- **THEN** the result SHALL include `"status": "error"` and a descriptive message

### Requirement: Re-ingestion replaces old chunks (upsert semantics)

When `ingest_path_async` processes a source whose `source_id` already has
durable rows, the system SHALL retain the last searchable attempt while it
parses, chunks, embeds, writes, and verifies the complete candidate attempt.
Only after verification SHALL it remove stale row IDs for that `source_id`.
Stable `chunk_id` values SHALL remain separate from attempt-specific vector-row
IDs so an identical forced re-ingestion cannot overwrite durable rows early.

#### Scenario: Re-ingest replaces chunks after verification
- **GIVEN** `paper.pdf` previously produced eight durable chunks
- **WHEN** `ingest_path_async("paper.pdf", collection_name="research")` writes and verifies a replacement
- **THEN** the old eight chunks SHALL remain searchable until verification succeeds
- **AND** stale rows for that `source_id` SHALL then be removed
- **AND** the result SHALL include the new `chunks_created` count and `"chunks_removed": 8`

#### Scenario: First-time ingest has nothing to remove
- **WHEN** `ingest_path_async("new_file.pdf")` processes a source whose `source_id` is absent
- **THEN** no stale rows SHALL be selected
- **AND** the result SHALL include `"chunks_removed": 0`

#### Scenario: Failed replacement preserves durable chunks
- **GIVEN** one source has a complete durable attempt
- **WHEN** its candidate parse, embedding, validation, write, or verification fails
- **THEN** the durable attempt MUST remain searchable
- **AND** no stale-row cleanup MUST delete it

### Requirement: CLI delete subcommand

The `rag-mcp` CLI SHALL provide a `delete` subcommand with three mutually-exclusive flags: `--path`, `--metadata`, and `--collection`. A `--dry-run` flag SHALL preview what would be deleted without executing. Only `--collection` SHALL require confirmation (it drops the entire collection), unless `--yes` is passed. Dry-run counts SHALL be produced by the same shared deletion preview logic used by the MCP delete tool.

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
- **THEN** the count SHALL match the shared deletion preview helper for the same inputs

#### Scenario: Validation — exactly one flag must be provided
- **WHEN** `rag-mcp delete` is executed with no flags, or with multiple mutually-exclusive flags
- **THEN** the CLI SHALL print an error message and exit with a non-zero status code

### Requirement: MCP delete_documents tool

The system SHALL expose a `delete_documents` MCP tool that accepts optional `path: str`, `metadata_filter: dict`, `collection: str` (default `"documents"`), and `dry_run: bool` (default `false`) parameters. When `collection` is provided without `path` or `metadata_filter`, the collection itself SHALL be dropped. Dry-run counts SHALL be produced by the same shared deletion preview logic used by the CLI delete subcommand.

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
- **THEN** the count SHALL match the CLI dry-run preview for the same path and collection

### Requirement: Stale-version selection is source-scoped

When replacing a source version, the selection of rows to delete SHALL be
scoped to that source's `source_id` at the store level. The implementation
SHALL NOT read the whole collection to find them.

The correctness guarantee is unchanged — only rows belonging to this
`source_id` and not to the current replacement attempt are deleted — but the
work performed SHALL be proportional to the source's own row count, not to the
collection's. The previous implementation iterated every row in the collection
for every replaced file, inside the global write lock, making re-ingestion
cost O(files × collection size) and blocking concurrent ingestion.

#### Scenario: Selection reads only the source's rows

- **GIVEN** a collection containing many sources
- **WHEN** one source is replaced
- **THEN** the number of rows read to select stale rows SHALL be proportional
  to that source's row count
- **AND** SHALL NOT be proportional to the collection's total row count

#### Scenario: Only stale rows of this source are deleted

- **GIVEN** a source with rows from a previous attempt and rows from the
  current verified attempt
- **WHEN** stale cleanup runs
- **THEN** exactly the previous attempt's rows SHALL be deleted
- **AND** no row of any other source SHALL be deleted, including a
  byte-identical file at another path

#### Scenario: Backends differing on missing-key inequality stay correct

- **GIVEN** a store whose filter semantics treat a missing metadata key
  differently under inequality
- **WHEN** stale selection runs
- **THEN** the attempt comparison SHALL be performed such that rows lacking
  the attempt key are not silently included or excluded by backend semantics

#### Scenario: Cleanup cost is observable

- **WHEN** a source is replaced
- **THEN** the existing `cleanup_seconds` stage timing SHALL continue to be
  reported for that source

