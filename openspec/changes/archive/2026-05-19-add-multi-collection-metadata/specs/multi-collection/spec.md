# Delta Specification: multi-collection

## ADDED Requirements

### Requirement: Collection-aware ingestion

The `ingest_path()` function SHALL accept an optional `collection_name: str = "documents"` parameter. When specified, documents SHALL be ingested into the named ChromaDB collection rather than the default `"documents"` collection. The collection SHALL be created automatically if it does not exist.

#### Scenario: Ingest into named collection
- **WHEN** `ingest_path(path="/papers", collection_name="research")` is called with a valid PDF
- **THEN** the document's chunks SHALL be stored in the `"research"` collection in ChromaDB
- **THEN** the `"research"` collection SHALL be created if it does not already exist
- **THEN** the result dict SHALL include `"collection": "research"`

#### Scenario: Default collection preservation
- **WHEN** `ingest_path(path="/papers")` is called without `collection_name`
- **THEN** the document's chunks SHALL be stored in the `"documents"` collection
- **THEN** the behaviour SHALL be identical to the current implementation

### Requirement: Collection-aware search

The search functions in `retrieval.py` SHALL accept an optional `collection_name: str = "documents"` parameter. The search SHALL query only the specified ChromaDB collection.

#### Scenario: Search named collection
- **WHEN** `search_documents("transformer", collection_name="research")` is called
- **THEN** results SHALL be retrieved only from the `"research"` collection
- **THEN** documents in other collections SHALL NOT appear in results

#### Scenario: Default collection search
- **WHEN** `search_documents("transformer")` is called without `collection_name`
- **THEN** results SHALL be retrieved from the default `"documents"` collection

### Requirement: List available collections

The system SHALL provide a function `list_collections() -> list[dict]` that returns all ChromaDB collections with their document and chunk counts.

#### Scenario: List all collections
- **WHEN** `list_collections()` is called after ingesting into `"research"` and `"code"` collections
- **THEN** the result SHALL include both `"research"` and `"code"` collection names
- **THEN** each collection entry SHALL include `name`, `document_count`, and `chunk_count`

#### Scenario: List when no collections exist
- **WHEN** `list_collections()` is called on a fresh ChromaDB with no ingested documents
- **THEN** the result SHALL be an empty list

### Requirement: Collection-aware file watcher

The `DocumentIngestHandler` SHALL accept an optional `collection_name: str = "documents"` parameter. Auto-ingested files SHALL be routed to the specified collection. The `watch_directory()` function SHALL pass a `--collection` CLI flag value to the handler.

#### Scenario: Watcher routes to named collection
- **WHEN** the watcher is started with `--collection research` and a new PDF is detected
- **THEN** the auto-ingested file SHALL be stored in the `"research"` collection

#### Scenario: Watcher uses default collection
- **WHEN** the watcher is started without `--collection` and a new PDF is detected
- **THEN** the auto-ingested file SHALL be stored in the `"documents"` collection

### Requirement: CLI collection flags

The `rag-mcp` CLI SHALL accept `--collection TEXT` on the `ingest`, `search`, `list`, and `watch` subcommands. A new `list-collections` subcommand SHALL display available collections.

#### Scenario: CLI ingest with collection
- **WHEN** `rag-mcp ingest ./papers --collection research` is executed
- **THEN** documents SHALL be ingested into the `"research"` collection

#### Scenario: CLI list-collections
- **WHEN** `rag-mcp list-collections` is executed
- **THEN** available collection names and their chunk counts SHALL be displayed

### Requirement: MCP tool collection parameter

The `ingest_documents`, `search_documents`, and `list_indexed_documents` MCP tools SHALL accept an optional `collection: string` parameter. A new `list_collections` MCP tool SHALL return available collections.

#### Scenario: MCP ingest with collection
- **WHEN** `ingest_documents(path="./papers", collection="research")` is called via MCP
- **THEN** the document SHALL be ingested into the `"research"` collection

#### Scenario: MCP search with collection
- **WHEN** `search_documents(query="transformer", collection="research")` is called via MCP
- **THEN** results SHALL be from the `"research"` collection only
