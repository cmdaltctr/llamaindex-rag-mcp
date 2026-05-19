## Why

The current RAG MCP server is purely pull-based — users must manually invoke `rag-mcp ingest` (or the `ingest_documents` MCP tool) every time a PDF or document is added or modified. For a Zotero workflow where papers accumulate organically, this creates friction: either you remember to re-ingest periodically, or your index drifts out of sync with your document library. A file watcher eliminates this gap by auto-ingesting new and changed documents as they appear.

This is especially relevant for Zotero storage — new papers land in `/Users/aizat/Zotero/storage/<hash>/` automatically when you add PDFs via Zotero connectors. A watcher on that directory means your RAG index stays current without any manual steps.

## What Changes

- **New CLI command `rag-mcp watch <path>`**: A long-running process that watches a directory tree (e.g. Zotero storage) for new and modified documents and auto-ingests them into the ChromaDB index. Includes SHA-256 content-hash deduplication, debouncing, ingestion throttling, consecutive-error detection, and graceful shutdown.
- **New module `src/rag_mcp/watcher.py`**: Contains the `watchdog`-based event handler with debouncing, SHA-256 content-hash deduplication, ingestion throttling, consecutive-error detection, and structured logging.
- **New dependency `watchdog`**: Cross-platform file system event monitoring library (macOS FSEvents, Linux inotify, Windows).
- **Optional new MCP tool `watch_directory`** (sketch, evaluated during design): Exposes file watching as an MCP tool if the server lifecycle can support it cleanly.
- **No breaking changes**: Existing `rag-mcp ingest`, `rag-mcp search`, and all MCP tools remain unchanged. Existing ChromaDB data is untouched.

## Capabilities

### New Capabilities

- `watch-command`: A new CLI subcommand (`rag-mcp watch <path>`) that monitors a directory for document events (file creation, modification) and calls `ingest_path()` to auto-index new/changed content. Includes per-file debouncing, SHA-256 content-hash deduplication, ingestion throttling (`BoundedSemaphore`), consecutive-`ConnectionError` detection, and a watcher-owned graceful shutdown sequence on SIGINT.

### Modified Capabilities

*(None — existing capabilities and their specs are unchanged.)*

## Impact

| Area | Impact |
|------|--------|
| **New dependency** | `watchdog` added to `pyproject.toml` — lightweight, pure Python, no system-level deps |
| **CLI** | New `watch` subcommand in `cli.py` |
| **Source** | New `src/rag_mcp/watcher.py` (~120 lines) |
| **ChromaDB** | No schema change. Existing vectors untouched. Watcher writes into the same persistent collection |
| **MCP tools** | No change to tool schemas or behaviour. Backward compatible |
| **Test surface** | New `tests/test_watcher.py` — 16 test cases with mocks for `Observer`, `FileSystemEvent`, `threading.Timer`, and `ingest_path`. Includes error-path coverage (ConnectionError, FileNotFoundError, corrupt file), throttling, debounce validation, and graceful shutdown. One `@pytest.mark.slow` integration test for real debounce timing |
| **Documentation** | `README` / CLI help updated with `watch` usage |
