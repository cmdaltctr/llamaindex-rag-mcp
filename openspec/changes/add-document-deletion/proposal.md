## Why

The RAG MCP server is append-only — once a document is ingested, its chunks live in ChromaDB forever. There is no CLI command, MCP tool, or internal function to delete documents, remove chunks by metadata filter, drop a collection, or clean up stale vectors when files are deleted from a watched directory. Re-ingesting the same file creates duplicate chunks. The watcher accumulates orphaned vectors from deleted files with no cleanup path. Users need the ability to remove documents and collections, and the system should automatically keep itself clean.

## What Changes

**Core deletion functions:**
- Add `remove_document(file_path, collection_name)` to `ingestion.py` — deletes all chunks matching a source file path via ChromaDB's `where` clause
- Add `remove_by_metadata(metadata_filter, collection_name)` to `ingestion.py` — deletes all chunks matching an arbitrary metadata filter (e.g., `{"category": "uncategorised"}`)
- Add `remove_collection(collection_name)` to `ingestion.py` — drops an entire ChromaDB collection

**Re-ingestion upsert (automatic):**
- Modify `ingest_path()` to call `remove_document()` for each file **before** embedding — re-ingesting a file replaces its chunks rather than appending duplicates. This is **BREAKING** behaviour (currently append-only, becomes replace-on-reingest).

**CLI commands:**
- New `rag-mcp delete` subcommand with three mutually-exclusive flags: `--path` (delete chunks for a file), `--metadata` (delete chunks matching a metadata filter), `--collection` (drop the entire collection)
- `--dry-run` flag on `delete` to preview what would be removed without executing
- `--yes` flag on `delete --collection` to skip the confirmation prompt
- Deletion by `--path` or `--metadata` does NOT require confirmation; deletion by `--collection` DOES (it drops the entire collection — irreversible)

**MCP tools:**
- New `delete_documents` MCP tool — accepts optional `path`, `metadata_filter`, `collection`, and `dry_run` parameters. When `collection` is provided without `path` or `metadata_filter`, the collection itself is dropped.
- No separate `delete_collection` MCP tool — collection drop is handled by `delete_documents` with only the `collection` parameter.

**Watcher integration:**
- Add `on_deleted` event handler to `DocumentIngestHandler` — when a file is deleted from a watched directory, its vectors are automatically removed from ChromaDB. No debouncing needed (deletion is idempotent). Cancels any pending ingest timer for the same file path.

## Capabilities

### New Capabilities

- `document-deletion`: Core deletion functionality — remove chunks by file path, by metadata filter, or drop collections entirely. Exposed via ingestion.py functions, the `delete_documents` MCP tool, and the `delete` CLI subcommand.

### Modified Capabilities

- `watch-command`: File watcher must add an `on_deleted` event handler that automatically removes vectors when watched files are deleted. The handler must cancel any pending ingest timers and clear hash cache entries for the deleted file path.

## Impact

| Area            | Impact                                                                                                |
| --------------- | ----------------------------------------------------------------------------------------------------- |
| **Source**          | `ingestion.py` — 3 new functions: `remove_document()`, `remove_by_metadata()`, `remove_collection()`; `ingest_path()` calls `remove_document()` before embedding (upsert) |
| **CLI**             | `cli.py` — 1 new subcommand: `delete` with three mutually-exclusive flags (`--path`, `--metadata`, `--collection`), plus `--dry-run` and `--yes` |
| **MCP tools**       | `server.py` — 1 new tool: `delete_documents` (handles all three deletion modes including collection drop) |
| **Watcher**         | `watcher.py` — new `on_deleted` handler; `_do_delete()` method; cancels timers and clears hash cache for deleted files |
| **ChromaDB**        | No schema change — uses existing `collection.delete(where=...)` and `client.delete_collection()` APIs |
| **Breaking**        | Re-ingestion behaviour changes: calling `ingest_path()` on a previously-ingested file now REPLACES chunks (upsert semantics) rather than appending duplicates. This is the only breaking change. All new features are additive with sensible defaults. |
| **Dependencies**    | Zero new Python dependencies. Uses ChromaDB's existing `delete()` API (already available). |
| **Safety**          | `--collection` (collection drop) requires CLI confirmation unless `--yes` is passed. `--dry-run` previews all operations without executing. Return values include `chunks_removed` count for verification. |
