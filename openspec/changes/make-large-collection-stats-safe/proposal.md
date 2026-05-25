## Why

Large collections are currently reported from only the first 10,000 chunks in several places. This silently undercounts indexed documents/chunks and can omit existing metadata categories, which becomes misleading once users index larger libraries.

## What Changes

- Introduce a shared ChromaDB pagination helper for metadata scans.
- Replace hardcoded `limit=10000` one-shot reads in document listing, collection listing, and category discovery.
- Add a central configuration constant for scan page size instead of scattered magic numbers.
- Ensure large scans either paginate to completion or explicitly report truncation when intentionally bounded.
- Preserve public MCP/CLI response shapes unless an optional diagnostic field is deliberately added.

## Capabilities

### New Capabilities
- `large-collection-statistics`: Accurate document/category statistics for ChromaDB collections larger than one fetch page.

### Modified Capabilities
- `metadata-extraction`: Existing category lookup SHALL consider all available category metadata, not only the first 10,000 chunks.

## Impact

- Affected code: `src/rag_mcp/config.py`, `src/rag_mcp/ingestion.py`, `src/rag_mcp/retrieval.py`, `src/rag_mcp/metadata_extractor.py`.
- Affected behavior: `list_indexed_documents`, `list_collections`, and Ollama/llamaindex metadata category prompts become accurate for large collections.
- No dependency, storage schema, or collection migration changes are expected.
