## 1. Core Deletion Functions in ingestion.py

- [x] 1.1 Implement `remove_document(file_path: str, collection_name: str = "documents") -> dict` — calls `collection.delete(where={"file_path": file_path})`, returns `{status, chunks_removed, collection}`
- [x] 1.2 Implement `remove_by_metadata(metadata_filter: dict, collection_name: str = "documents") -> dict` — calls `collection.delete(where=metadata_filter)`, returns `{status, chunks_removed, collection}`
- [x] 1.3 Implement `remove_collection(collection_name: str) -> dict` — calls `client.delete_collection(name)`, returns `{status, collection}`
- [x] 1.4 Handle edge cases: non-existent collection, empty where filter, empty collection

## 2. Re-Ingestion Upsert in ingestion.py

- [x] 2.1 Modify `ingest_path()` to call `remove_document()` for each file BEFORE `_read_and_chunk_file()`
- [x] 2.2 Update `ingest_path()` result dict to include `"chunks_removed"` field reflecting the count of replaced chunks
- [x] 2.3 Ensure `remove_document()` is called even when `workers > 1` (parallel ingestion path)

## 3. CLI Commands

- [x] 3.1 Add `rag-mcp delete` subcommand with three mutually-exclusive flags: `--path`, `--metadata`, `--collection`
- [x] 3.2 Add `--dry-run` flag to `delete` subcommand — previews deletion without modifying ChromaDB
- [x] 3.3 Add confirmation prompt for `--collection` (drops entire collection) unless `--yes` is passed
- [x] 3.4 Add `--collection` flag on `delete` to scope chunk-level deletion to a specific ChromaDB collection (when combined with `--path` or `--metadata`)
- [x] 3.5 Validate that exactly one of `--path`, `--metadata`, `--collection` is provided
- [x] 3.6 Display chunk counts in human-readable format (Rich table) and JSON (`--json`)

## 4. MCP Tools

- [x] 4.1 Add `delete_documents` MCP tool to `server.py` — accepts `path`, `metadata_filter`, `collection`, `dry_run`. When only `collection` is provided, drops the collection.
- [x] 4.2 Update tool discovery test to expect 5 tools (up from 4)

## 5. Watcher Integration

- [x] 5.1 Add `on_deleted(self, event)` method to `DocumentIngestHandler` in `watcher.py`
- [x] 5.2 Add `_do_delete(self, file_path: str)` method — cancels pending ingest timer, clears hash cache, calls `remove_document()`
- [x] 5.3 Handle the case where a file was modified then deleted before the debounce timer fired
- [x] 5.4 Log deletion success at INFO level with chunk count; log failures at WARNING level

## 6. Testing

- [x] 6.1 Test `remove_document()` — deletes existing file chunks, returns correct count
- [x] 6.2 Test `remove_document()` — with non-existent file returns `chunks_removed: 0`
- [x] 6.3 Test `remove_document()` — with non-existent collection returns error
- [x] 6.4 Test `remove_by_metadata()` — deletes by category filter, returns count
- [x] 6.5 Test `remove_collection()` — drops collection, subsequent list doesn't include it
- [x] 6.6 Test `remove_collection()` — on non-existent collection returns error
- [x] 6.7 Test re-ingestion upsert — ingesting same file twice replaces chunks, no duplicates
- [x] 6.8 Test re-ingestion upsert — first-time ingest still works unchanged
- [x] 6.9 Test CLI `delete --path` — removes chunks, displays count
- [x] 6.10 Test CLI `delete --metadata` — removes matching chunks
- [x] 6.11 Test CLI `delete --collection` — prompts for confirmation, drops collection
- [x] 6.12 Test CLI `delete --collection --yes` — drops without confirmation
- [x] 6.13 Test CLI `delete --dry-run` — previews without deleting
- [x] 6.14 Test CLI `delete` — rejects when no flag or multiple flags provided
- [x] 6.15 Test MCP `delete_documents` — by path, by metadata, drop collection, dry_run
- [x] 6.16 Test MCP tool discovery includes `delete_documents`
- [x] 6.17 Test watcher `on_deleted` — auto-removes vectors when file deleted
- [x] 6.18 Test watcher `on_deleted` — cancels pending ingest timer for same file
- [x] 6.19 Test watcher `on_deleted` — uses handler's configured collection
- [x] 6.20 Test watcher `on_deleted` — ignored for unsupported file types
- [x] 6.21 Run `uv run pytest -m "not slow"` and confirm all tests pass
- [x] 6.22 Run `uv run pytest --cov=rag_mcp --cov-report=term-missing` and confirm core module coverage

## 7. Documentation

- [x] 7.1 Create ADR-012 for document deletion
- [x] 7.2 Update README.md with new `delete` CLI subcommand
- [x] 7.3 Update README.md Tools table with `delete_documents` MCP tool
- [x] 7.4 Update AGENTS.md with deletion conventions
- [x] 7.5 Add docstrings to all new public functions
- [x] 7.6 Review all new log messages and docstrings for British English spelling
