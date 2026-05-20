## 1. Configuration

- [x] 1.1 Add `METADATA_EXTRACTION_MODE` env var to `config.py` (default `"keyword"`, allowed values: `"disabled"`, `"keyword"`, `"ollama"`, `"llamaindex"`)
- [x] 1.2 Add `METADATA_KEYWORD_RULES` env var to `config.py` (optional JSON string, default `None` — uses built-in rules when not set)
- [x] 1.3 Add `OLLAMA_CLASSIFY_MODEL` env var to `config.py` (default `"qwen3:0.6b"`, only used in `"ollama"` mode)
- [x] 1.4 Update `COLLECTION_NAME` in `config.py` to be a configurable default (kept as `"documents"` for backward compat, used when no `--collection` flag is passed)

## 2. Metadata Extraction Module

- [x] 2.1 Create `src/rag_mcp/metadata_extractor.py` with `extract_metadata(file_text: str, file_name: str) -> dict` as the public API
- [x] 2.2 Implement `_extract_disabled()` — returns `{}`
- [x] 2.3 Implement `_extract_keyword(text: str) -> dict` — regex pattern matching with scoring, returns `{"category": "<best>"}` or `{"category": "uncategorised"}`
- [x] 2.4 Define default keyword rules covering: AI, Philosophy, Biology, Marketing, Programming (per design doc)
- [x] 2.5 Implement `_load_keyword_rules()` — loads custom rules from `METADATA_KEYWORD_RULES` JSON, falls back to defaults on parse error with WARNING log
- [x] 2.6 Implement `_extract_ollama(text: str) -> dict` — POST to `OLLAMA_BASE_URL/api/generate`, returns `{"category": result}` on success, `{"category": "uncategorised"}` on failure with WARNING log
- [x] 2.7 Implement `_extract_llamaindex(text: str, file_name: str) -> dict` — stub that logs INFO "MetadataExtractor not yet implemented — falling back to keyword mode" and calls `_extract_keyword()`
- [x] 2.8 Add module-level routing in `extract_metadata()` — switch on `METADATA_EXTRACTION_MODE` to dispatch to the correct extraction function

## 3. Collection-Aware Ingestion

- [x] 3.1 Update `_get_chroma_collection()` in `ingestion.py` to accept `collection_name: str = "documents"` parameter
- [x] 3.2 Thread `collection_name` parameter through `ingest_path()`, `_ingest_sequential()`, `_ingest_parallel()`
- [x] 3.3 Thread `collection_name` through `_embed_and_write()` and `_embed_and_write_concurrent()`
- [x] 3.4 Return `"collection"` field in `ingest_path()` result dict
- [x] 3.5 Update `list_documents()` to accept optional `collection_name` parameter

## 4. Metadata Attachment in Ingestion

- [x] 4.1 In `_read_and_chunk_file()`, after `documents = reader.load_data()`, extract full text and call `extract_metadata()`
- [x] 4.2 Attach extracted metadata to every node's `.metadata` dict before returning nodes
- [x] 4.3 Verify metadata is stored in ChromaDB by checking `collection.get(include=["metadatas"])` in a test

## 5. Collection-Aware Retrieval

- [x] 5.1 Add `collection_name: str = "documents"` parameter to `search_documents()` in `retrieval.py`
- [x] 5.2 Add optional `metadata_filter: dict | None = None` parameter to `search_documents()`
- [x] 5.3 Pass `where=metadata_filter` to ChromaDB `collection.query()` when `metadata_filter` is provided
- [x] 5.4 Implement `list_collections() -> list[dict]` function in `retrieval.py` — iterates ChromaDB collections, returns name + count per collection

## 6. Watcher Collection Support

- [x] 6.1 Add `collection_name: str = "documents"` parameter to `DocumentIngestHandler.__init__()`
- [x] 6.2 Pass `collection_name` to `ingest_path()` call inside `_do_ingest()`
- [x] 6.3 Update `watch_directory()` to accept `collection_name` parameter and pass to `DocumentIngestHandler`

## 7. CLI Integration

- [x] 7.1 Add `--collection TEXT` option to `rag-mcp ingest` subcommand in `cli.py`
- [x] 7.2 Add `--collection TEXT` option to `rag-mcp search` subcommand in `cli.py`
- [x] 7.3 Add `--collection TEXT` option to `rag-mcp watch` subcommand in `cli.py`
- [x] 7.4 Add `--collection TEXT` option to `rag-mcp list` subcommand in `cli.py`
- [x] 7.5 Add new `rag-mcp list-collections` subcommand — calls `list_collections()` and displays results via rich table

## 8. MCP Tool Updates

- [x] 8.1 Add optional `collection: str = "documents"` parameter to `ingest_documents` MCP tool handler in `server.py`
- [x] 8.2 Add optional `collection: str = "documents"` parameter to `search_documents` MCP tool handler
- [x] 8.3 Add optional `collection: str = "documents"` parameter to `list_indexed_documents` MCP tool handler
- [x] 8.4 Add new `list_collections` MCP tool — returns available collections with counts

## 9. Testing

- [x] 9.1 Test `metadata_extractor.py` keyword mode — correct categorisation for known-rule text, multiple-match scoring, uncategorised fallback
- [x] 9.2 Test `metadata_extractor.py` disabled mode — returns `{}`
- [x] 9.3 Test `metadata_extractor.py` custom keyword rules via `METADATA_KEYWORD_RULES` JSON
- [x] 9.4 Test `metadata_extractor.py` llamaindex stub — logs INFO, falls back to keyword
- [x] 9.5 Test `ingest_path()` with collection routing — file lands in specified collection, `"collection"` field in result
- [x] 9.6 Test `ingest_path()` default collection — file lands in `"documents"` when no collection specified
- [x] 9.7 Test metadata attachment — ingested chunks have `"category"` metadata in ChromaDB
- [x] 9.8 Test `search_documents()` with collection routing — only returns results from specified collection
- [x] 9.9 Test `search_documents()` with metadata filter — only returns chunks matching `{"category": "AI"}`
- [x] 9.10 Test `list_collections()` — returns correct collection names and counts
- [x] 9.11 Test watcher with `--collection` — auto-ingested files go to specified collection
- [x] 9.12 Test CLI `--collection` flag on `ingest`, `search`, `watch`, `list` subcommands
- [x] 9.13 Test CLI `list-collections` subcommand output
- [x] 9.14 Test MCP tools with optional `collection` parameter
- [x] 9.15 Test backward compatibility — all commands without `--collection` behave identically to pre-change
- [x] 9.16 Run `uv run pytest -m "not slow"` and confirm all tests pass
- [x] 9.17 Run `uv run pytest --cov=rag_mcp --cov-report=term-missing` and confirm coverage ≥ 85%

## 10. Documentation

- [x] 10.1 Update `.env.example` with new env vars (`METADATA_EXTRACTION_MODE`, `METADATA_KEYWORD_RULES`, `OLLAMA_CLASSIFY_MODEL`)
- [x] 10.2 Update AGENTS.md with multi-collection conventions and metadata extraction overview
- [x] 10.3 Add docstrings to all new public functions in `metadata_extractor.py`, updated functions in `ingestion.py`, `retrieval.py`
- [x] 10.4 Review all new log messages and docstrings for British English spelling
