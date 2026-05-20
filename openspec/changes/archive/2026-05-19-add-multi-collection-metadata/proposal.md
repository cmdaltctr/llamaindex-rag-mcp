## Why

Currently all ingested documents land in a single `documents` collection in ChromaDB. For users with diverse content (research papers, code docs, philosophy notes, marketing materials), this creates a monolithic index where a query about "attention mechanisms" could return results from a marketing PDF alongside a transformer paper. We need the ability to separate content into named collections at ingest time, plus automatic content-based tagging for fine-grained filtering within each collection.

## What Changes

**Multi-collection support:**
- Add explicit `--collection` flag to `rag-mcp ingest`, `rag-mcp watch`, and `rag-mcp search` CLI commands
- Add optional `collection` parameter to the `ingest_documents`, `search_documents`, and `list_indexed_documents` MCP tools
- Add a new `rag-mcp list-collections` CLI command and `list_collections` MCP tool to show available collections
- Default collection name remains `"documents"` for backward compatibility — no **BREAKING** changes

**Auto-metadata extraction:**
- Add a configurable `METADATA_EXTRACTION_MODE` env var (values: `disabled`, `keyword`, `ollama`, `llamaindex`)
- Implement keyword-based categorisation using user-definable regex rules (zero additional dependencies)
- Implement Ollama LLM-based categorisation as a smarter fallback (requires a chat model like `qwen3:0.6b`)
- Stub out LlamaIndex MetadataExtractor integration for future use
- Extracted metadata (e.g., `{"category": "AI"}`) is stored as ChromaDB metadata on every chunk

**Integration:**
- `DocumentIngestHandler` (file watcher) routes files to the correct collection based on its `--collection` flag
- Search operations can optionally filter results by metadata fields (e.g., `--filter '{"category":"AI"}'`)

## Capabilities

### New Capabilities

- `multi-collection`: Named document collections in ChromaDB — explicit user control over which collection receives ingested documents and which collection is searched. Includes `list-collections` to discover available collections.
- `metadata-extraction`: Configurable auto-categorisation of documents during ingestion. Supports keyword rules, Ollama LLM classification, and future LlamaIndex MetadataExtractor integration. Togglable via `METADATA_EXTRACTION_MODE` env var.

### Modified Capabilities

- `watch-command`: File watcher must accept a `--collection` parameter and route auto-ingested files to the specified collection. Search filtering must accept a metadata filter that works with auto-extracted tags.

## Impact

| Area            | Impact                                                                                                |
| --------------- | ----------------------------------------------------------------------------------------------------- |
| **Source**          | `config.py` — 2 new env vars (`METADATA_EXTRACTION_MODE`, `METADATA_KEYWORD_RULES`); `ingestion.py` — collection param plumbing + metadata attachment; `retrieval.py` — collection-aware search; `cli.py` — new flags and `list-collections` subcommand; `server.py` — optional `collection` param on MCP tools; `watcher.py` — `collection` param on handler |
| **New module**      | `rag_mcp/metadata_extractor.py` — metadata extraction logic (keyword, ollama, llamaindex modes)          |
| **Tests**           | `tests/test_ingestion.py` — collection routing + metadata attachment; `tests/test_watcher.py` — watcher collection routing; `tests/test_retrieval.py` — collection-aware search; `tests/test_cli.py` — new `--collection` flag; `tests/test_metadata_extractor.py` — new test file |
| **ChromaDB**        | No schema change — multiple collections share the same `chroma_db` directory and embedding dimension   |
| **Breaking**        | None. All new parameters are optional with sensible defaults (`collection` defaults to `"documents"`, extraction defaults to `"keyword"`). |
| **MCP tools**       | All three tools gain optional `collection: string` parameter; new `list_collections` tool added        |
| **Dependencies**    | Zero new Python dependencies. Keyword mode uses `re` (stdlib). Ollama mode uses `requests` (already depended via httpx). LlamaIndex stubs are no-op until an LLM is configured. |
