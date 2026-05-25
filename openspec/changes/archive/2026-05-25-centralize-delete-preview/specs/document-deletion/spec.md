## MODIFIED Requirements

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

#### Scenario: Dry run preview
- **WHEN** `rag-mcp delete --path /file.pdf --dry-run` is executed
- **THEN** the CLI SHALL display "Would delete N chunks" but SHALL NOT modify ChromaDB
- **THEN** the count SHALL match the shared deletion preview helper for the same inputs

### Requirement: MCP delete_documents tool
The system SHALL expose a `delete_documents` MCP tool that accepts optional `path: str`, `metadata_filter: dict`, `collection: str` (default `"documents"`), and `dry_run: bool` (default `false`) parameters. When `collection` is provided without `path` or `metadata_filter`, the collection itself SHALL be dropped. Dry-run counts SHALL be produced by the same shared deletion preview logic used by the CLI delete subcommand.

#### Scenario: MCP delete by file path
- **WHEN** `delete_documents(path="/path/to/file.pdf", collection="research")` is called via MCP
- **THEN** all chunks for that file SHALL be removed and the result SHALL include `"chunks_removed"`

#### Scenario: MCP delete by metadata filter
- **WHEN** `delete_documents(metadata_filter={"category": "uncategorised"})` is called via MCP
- **THEN** all matching chunks SHALL be removed

#### Scenario: MCP dry run
- **WHEN** `delete_documents(path="/file.pdf", dry_run=true)` is called via MCP
- **THEN** the result SHALL include `"would_delete": N` but no chunks SHALL be removed
- **THEN** the count SHALL match the CLI dry-run preview for the same path and collection
